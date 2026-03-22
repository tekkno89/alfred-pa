"""Triage event router — routes Slack events to the triage pipeline."""

import logging
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.repositories import UserRepository
from app.db.repositories.triage import MonitoredChannelRepository, TriageUserSettingsRepository
from app.services.focus import FocusModeService
from app.services.triage_cache import TriageCacheService

logger = logging.getLogger(__name__)


class TriageEventRouter:
    """Routes incoming Slack events to triage processing for eligible users."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.cache = TriageCacheService()
        self.user_repo = UserRepository(db)
        self.focus_service = FocusModeService(db)
        self.channel_repo = MonitoredChannelRepository(db)
        self.settings_repo = TriageUserSettingsRepository(db)

    async def route_event(
        self,
        event: dict[str, Any],
        authorizations: list[dict[str, Any]] | None,
    ) -> None:
        """Route a Slack event to triage processing for eligible Alfred users.

        Called from slack.py after focus mode processing. Determines which
        Alfred users should have this message triaged, then enqueues an
        ARQ job per user.
        """
        channel_id = event.get("channel", "")
        sender_slack_id = event.get("user", "")
        message_ts = event.get("ts", "")
        thread_ts = event.get("thread_ts")
        text = event.get("text", "")
        bot_id = event.get("bot_id")

        # Skip messages from bots by default (include overrides checked per-user later)
        is_bot_message = bool(bot_id)

        is_dm = channel_id.startswith("D")

        if is_dm:
            await self._route_dm(
                channel_id=channel_id,
                sender_slack_id=sender_slack_id,
                message_ts=message_ts,
                thread_ts=thread_ts,
                text=text,
                is_bot_message=is_bot_message,
                authorizations=authorizations or [],
            )
        else:
            # Check if this channel is monitored (O(1) Redis lookup)
            if not await self.cache.is_monitored_channel(channel_id):
                return
            await self._route_channel(
                channel_id=channel_id,
                sender_slack_id=sender_slack_id,
                message_ts=message_ts,
                thread_ts=thread_ts,
                text=text,
                is_bot_message=is_bot_message,
            )

    async def _route_dm(
        self,
        channel_id: str,
        sender_slack_id: str,
        message_ts: str,
        thread_ts: str | None,
        text: str,
        is_bot_message: bool,
        authorizations: list[dict[str, Any]],
    ) -> None:
        """Route a DM to triage for the recipient."""
        for auth_entry in authorizations:
            auth_user_id = auth_entry.get("user_id")
            is_bot_auth = auth_entry.get("is_bot", False)

            # Skip bot authorizations and sender's own authorization
            if is_bot_auth or auth_user_id == sender_slack_id:
                continue

            recipient = await self.user_repo.get_by_slack_id(auth_user_id)
            if not recipient:
                continue

            if await self._should_triage(recipient.id, is_bot_message):
                await self._enqueue_triage(
                    user_id=recipient.id,
                    event_type="dm",
                    channel_id=channel_id,
                    sender_slack_id=sender_slack_id,
                    message_ts=message_ts,
                    thread_ts=thread_ts,
                    text=text,
                )

    async def _route_channel(
        self,
        channel_id: str,
        sender_slack_id: str,
        message_ts: str,
        thread_ts: str | None,
        text: str,
        is_bot_message: bool,
    ) -> None:
        """Route a monitored channel message to triage for all monitoring users."""
        monitored = await self.channel_repo.get_users_for_channel(channel_id)
        for mc in monitored:
            # Skip if sender is the user themselves
            user = await self.user_repo.get(mc.user_id)
            if user and user.slack_user_id == sender_slack_id:
                continue

            if await self._should_triage(mc.user_id, is_bot_message):
                await self._enqueue_triage(
                    user_id=mc.user_id,
                    event_type="channel",
                    channel_id=channel_id,
                    sender_slack_id=sender_slack_id,
                    message_ts=message_ts,
                    thread_ts=thread_ts,
                    text=text,
                )

    async def _should_triage(self, user_id: str, is_bot_message: bool) -> bool:
        """Check if triage should run for this user.

        Triage is active when:
        - User is in focus mode, OR
        - User has is_always_on enabled
        """
        settings = await self.settings_repo.get_by_user_id(user_id)
        if not settings:
            return False

        in_focus = await self.focus_service.is_in_focus_mode(user_id)
        if not in_focus and not settings.is_always_on:
            return False

        # Default: skip bot messages (per-user include overrides checked in pipeline)
        if is_bot_message:
            return False

        return True

    async def _enqueue_triage(
        self,
        user_id: str,
        event_type: str,
        channel_id: str,
        sender_slack_id: str,
        message_ts: str,
        thread_ts: str | None,
        text: str,
    ) -> None:
        """Enqueue an ARQ job to process this message through the triage pipeline."""
        try:
            from app.worker.scheduler import get_redis_pool

            pool = await get_redis_pool()
            await pool.enqueue_job(
                "process_triage_job",
                user_id=user_id,
                event_type=event_type,
                channel_id=channel_id,
                sender_slack_id=sender_slack_id,
                message_ts=message_ts,
                thread_ts=thread_ts,
                message_text=text,
            )
            logger.debug(
                f"Enqueued triage job for user={user_id} "
                f"event_type={event_type} channel={channel_id}"
            )
        except Exception:
            logger.exception(f"Failed to enqueue triage job for user={user_id}")
