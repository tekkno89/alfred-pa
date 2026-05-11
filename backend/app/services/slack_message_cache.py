"""Slack message cache service for non-sensitive public channels."""

import logging
from datetime import datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.slack_message_cache import SlackMessageCache
from app.db.repositories.triage import MonitoredChannelRepository

logger = logging.getLogger(__name__)

MESSAGE_TTL_DAYS = 7


class SlackMessageCacheService:
    """Manages the workspace-scoped message cache for non-sensitive public channels.

    Cache Rules:
    - Public channels with sensitive=false: CACHED (7-day TTL)
    - Public channels with sensitive=true: NOT cached
    - Private channels: NOT cached (sensitive defaults to true)
    - DMs: NOT cached (hardcoded, never stored)
    """

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self._channel_repo: MonitoredChannelRepository | None = None

    @property
    def channel_repo(self) -> MonitoredChannelRepository:
        if self._channel_repo is None:
            self._channel_repo = MonitoredChannelRepository(self.db)
        return self._channel_repo

    async def get_message(
        self,
        workspace_id: str,
        channel_id: str,
        message_ts: str,
    ) -> str | None:
        """Get cached message text, or None if not cached."""
        result = await self.db.execute(
            select(SlackMessageCache).where(
                SlackMessageCache.workspace_id == workspace_id,
                SlackMessageCache.channel_id == channel_id,
                SlackMessageCache.message_ts == message_ts,
            )
        )
        cached = result.scalar_one_or_none()
        return cached.text if cached else None

    async def get_thread_messages(
        self,
        workspace_id: str,
        channel_id: str,
        thread_ts: str,
    ) -> list[tuple[str, str, str]]:
        """Get all cached messages in a thread.

        Returns list of (sender_slack_id, text, message_ts) tuples.
        """
        result = await self.db.execute(
            select(SlackMessageCache)
            .where(
                SlackMessageCache.workspace_id == workspace_id,
                SlackMessageCache.channel_id == channel_id,
                SlackMessageCache.parent_thread_ts == thread_ts,
            )
            .order_by(SlackMessageCache.created_at)
        )
        messages = result.fetchall()
        return [(m.sender_slack_id, m.text, m.message_ts) for m in messages]

    async def should_cache(
        self,
        user_id: str,
        channel_id: str,
    ) -> bool:
        """Check if messages from this channel should be cached.

        Returns True only for public non-sensitive channels.
        """
        mc = await self.channel_repo.get_by_user_and_channel(user_id, channel_id)
        if not mc:
            return False
        if mc.channel_type == "private":
            return False
        return not mc.sensitive

    async def fetch_and_cache(
        self,
        workspace_id: str,
        channel_id: str,
        message_ts: str,
        slack_service,
        user_id: str,
    ) -> str | None:
        """Fetch message from Slack and cache if allowed.

        Returns message text or None if fetch failed.
        """
        msg_data = await slack_service.get_message(channel_id, message_ts)
        if not msg_data:
            return None

        text = msg_data.get("text", "")
        sender_id = msg_data.get("user", msg_data.get("bot_id", "unknown"))
        is_bot = msg_data.get("bot_id") is not None
        thread_ts = msg_data.get("thread_ts")

        if thread_ts == message_ts:
            thread_ts = None

        created_at = None
        try:
            ts_float = float(message_ts)
            created_at = datetime.utcfromtimestamp(ts_float)
        except (ValueError, TypeError):
            pass

        if await self.should_cache(user_id, channel_id):
            cached = SlackMessageCache(
                workspace_id=workspace_id,
                channel_id=channel_id,
                message_ts=message_ts,
                parent_thread_ts=thread_ts,
                sender_slack_id=sender_id,
                text=text,
                is_bot=is_bot,
                created_at=created_at,
            )
            self.db.add(cached)
            await self.db.commit()
            logger.debug(f"Cached message {channel_id}/{message_ts}")

        return text

    async def cache_thread(
        self,
        workspace_id: str,
        channel_id: str,
        thread_ts: str,
        slack_service,
        user_id: str,
    ) -> list[tuple[str, str, str]]:
        """Fetch and cache all messages in a thread.

        Returns list of (sender_slack_id, text, message_ts) tuples.
        """
        messages = await slack_service.get_thread_messages(channel_id, thread_ts)
        results = []

        can_cache = await self.should_cache(user_id, channel_id)

        for msg in messages:
            msg_ts = msg.get("ts")
            text = msg.get("text", "")
            sender_id = msg.get("user", msg.get("bot_id", "unknown"))
            is_bot = msg.get("bot_id") is not None

            created_at = None
            try:
                ts_float = float(msg_ts)
                created_at = datetime.utcfromtimestamp(ts_float)
            except (ValueError, TypeError):
                pass

            if can_cache:
                parent_ts = thread_ts if msg_ts != thread_ts else None
                cached = SlackMessageCache(
                    workspace_id=workspace_id,
                    channel_id=channel_id,
                    message_ts=msg_ts,
                    parent_thread_ts=parent_ts,
                    sender_slack_id=sender_id,
                    text=text,
                    is_bot=is_bot,
                    created_at=created_at,
                )
                self.db.add(cached)

            results.append((sender_id, text, msg_ts))

        if can_cache:
            await self.db.commit()

        return results

    async def cleanup_expired(self) -> int:
        """Delete messages older than TTL. Called by nightly job.

        Returns count of deleted rows.
        """
        cutoff = datetime.utcnow() - timedelta(days=MESSAGE_TTL_DAYS)
        result = await self.db.execute(
            delete(SlackMessageCache).where(SlackMessageCache.cached_at < cutoff)
        )
        deleted = result.rowcount
        await self.db.commit()
        logger.info(
            f"Cleaned up {deleted} expired cache entries older than {MESSAGE_TTL_DAYS} days"
        )
        return deleted
