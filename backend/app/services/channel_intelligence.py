"""Channel intelligence service for participation tracking and LLM summaries."""

import asyncio
import logging
from datetime import datetime
from typing import Any

from slack_sdk.errors import SlackApiError
from slack_sdk.web.async_client import AsyncWebClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.repositories import OAuthTokenRepository
from app.db.repositories.slack_search import (
    SlackChannelSummaryRepository,
    UserChannelParticipationRepository,
)
from app.services.token_encryption import TokenEncryptionService

logger = logging.getLogger(__name__)

MAX_CHANNELS_PER_SUMMARY_RUN = 100
MIN_SUBSTANTIVE_MESSAGES = 3


class ChannelIntelligenceService:
    """Service for building channel participation rankings and LLM summaries."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.token_repo = OAuthTokenRepository(db)
        self.token_encryption = TokenEncryptionService(db)
        self.participation_repo = UserChannelParticipationRepository(db)
        self.summary_repo = SlackChannelSummaryRepository(db)

    async def _get_user_client(self, user_id: str) -> AsyncWebClient | None:
        """Get a Slack client using the user's OAuth token."""
        token = await self.token_repo.get_by_user_and_provider(user_id, "slack")
        if not token:
            return None
        access_token = await self.token_encryption.get_decrypted_access_token(token)
        return AsyncWebClient(token=access_token)

    async def update_participation(self, user_id: str) -> int:
        """Update channel participation data for a user.

        Calls users.conversations to get all channels the user is in,
        sorted by most recently updated, and stores the top 100.

        Returns the number of channels stored.
        """
        client = await self._get_user_client(user_id)
        if not client:
            logger.warning(f"No Slack token for user {user_id}, skipping participation update")
            return 0

        channels: list[dict[str, Any]] = []
        # Cache user ID → display name for DM channel naming
        user_name_cache: dict[str, str] = {}
        cursor = None
        max_retries = 3

        while True:
            for attempt in range(max_retries + 1):
                try:
                    kwargs: dict[str, Any] = {
                        "types": "public_channel,private_channel,mpim,im",
                        "exclude_archived": False,
                        "limit": 200,
                    }
                    if cursor:
                        kwargs["cursor"] = cursor

                    response = await client.users_conversations(**kwargs)

                    for ch in response.get("channels", []):
                        channel_type = "public"
                        if ch.get("is_im"):
                            channel_type = "im"
                        elif ch.get("is_mpim"):
                            channel_type = "mpim"
                        elif ch.get("is_private") or ch.get("is_group"):
                            channel_type = "private"

                        # For DM channels, resolve the other user's name
                        channel_name = ch.get("name", ch["id"])
                        if channel_type == "im" and ch.get("user"):
                            dm_user_id = ch["user"]
                            if dm_user_id not in user_name_cache:
                                try:
                                    user_resp = await client.users_info(user=dm_user_id)
                                    u = user_resp.get("user", {})
                                    user_name_cache[dm_user_id] = (
                                        u.get("profile", {}).get("display_name")
                                        or u.get("profile", {}).get("real_name")
                                        or u.get("real_name")
                                        or dm_user_id
                                    )
                                except SlackApiError:
                                    user_name_cache[dm_user_id] = dm_user_id
                            channel_name = user_name_cache[dm_user_id]

                        channels.append(
                            {
                                "channel_id": ch["id"],
                                "channel_name": channel_name,
                                "channel_type": channel_type,
                                "is_member": ch.get("is_member", True),
                                "is_archived": ch.get("is_archived", False),
                                "member_count": ch.get("num_members", 0),
                                "last_activity_at": _unix_to_datetime(
                                    ch.get("updated", 0)
                                ),
                            }
                        )

                    cursor = (
                        response.get("response_metadata", {}).get("next_cursor")
                    )
                    break  # Success, exit retry loop

                except SlackApiError as e:
                    if e.response.get("error") == "ratelimited" and attempt < max_retries:
                        retry_after = int(
                            e.response.headers.get("Retry-After", 5)
                        )
                        logger.warning(
                            f"Rate limited on users.conversations, retrying in {retry_after}s"
                        )
                        await asyncio.sleep(retry_after)
                    else:
                        logger.error(
                            f"Error fetching conversations for user {user_id}: "
                            f"{e.response.get('error', 'unknown')}"
                        )
                        # Return what we have so far
                        break

            if not cursor:
                break

        # Sort by last_activity_at (most recent first) and take top 100
        channels.sort(
            key=lambda c: c.get("last_activity_at") or datetime.min, reverse=True
        )
        channels = channels[:100]

        count = await self.participation_repo.upsert_batch(user_id, channels)
        logger.info(
            f"Updated participation for user {user_id}: {count} channels"
        )
        return count

    async def update_summaries(self) -> int:
        """Generate LLM summaries for channels across all users.

        Collects unique channels from all users' participation data,
        reads recent messages, and generates summaries with an LLM.

        Returns the number of summaries generated.
        """
        from sqlalchemy import select

        from app.db.models.oauth_token import UserOAuthToken

        # Get all users with Slack OAuth tokens
        result = await self.db.execute(
            select(UserOAuthToken).where(UserOAuthToken.provider == "slack")
        )
        tokens = list(result.scalars().all())
        if not tokens:
            logger.info("No Slack tokens found, skipping summary generation")
            return 0

        # Collect unique channels from all users' participation data
        # Track which user has access to each channel
        channel_users: dict[str, tuple[str, str]] = {}  # channel_id -> (user_id, channel_type)
        channel_info: dict[str, dict[str, Any]] = {}

        for token in tokens:
            user_channels = await self.participation_repo.get_by_user(
                token.user_id, limit=100, include_archived=False
            )
            for ch in user_channels:
                if ch.channel_id not in channel_users:
                    channel_users[ch.channel_id] = (token.user_id, ch.channel_type)
                    channel_info[ch.channel_id] = {
                        "channel_name": ch.channel_name,
                        "channel_type": ch.channel_type,
                        "member_count": ch.member_count,
                        "is_archived": ch.is_archived,
                    }
                # For public channels, any user's token works
                # For private channels, keep the first user who has access
                elif ch.channel_type == "public" and channel_users[ch.channel_id][1] != "public":
                    channel_users[ch.channel_id] = (token.user_id, ch.channel_type)

        # Skip DMs (im type) — too personal to summarize
        channel_ids_to_summarize = [
            cid for cid, (_, ctype) in channel_users.items()
            if ctype != "im"
        ][:MAX_CHANNELS_PER_SUMMARY_RUN]

        summarized = 0
        for channel_id in channel_ids_to_summarize:
            user_id, _ = channel_users[channel_id]
            info = channel_info[channel_id]

            try:
                summary = await self._summarize_channel(
                    user_id, channel_id, info["channel_name"]
                )
                if summary:
                    await self.summary_repo.upsert(
                        channel_id=channel_id,
                        channel_name=info["channel_name"],
                        channel_type=info["channel_type"],
                        summary=summary,
                        member_count=info["member_count"],
                        is_archived=info["is_archived"],
                        generated_by_user_id=user_id,
                    )
                    summarized += 1
            except Exception as e:
                logger.error(
                    f"Error summarizing channel {channel_id}: {e}"
                )

            # Rate limit spacing
            await asyncio.sleep(1)

        logger.info(f"Generated {summarized} channel summaries")
        return summarized

    async def _summarize_channel(
        self, user_id: str, channel_id: str, channel_name: str
    ) -> str | None:
        """Read recent messages from a channel and generate an LLM summary."""
        client = await self._get_user_client(user_id)
        if not client:
            return None

        try:
            response = await client.conversations_history(
                channel=channel_id, limit=50
            )
            messages = response.get("messages", [])
        except SlackApiError as e:
            logger.warning(
                f"Cannot read channel {channel_id}: {e.response.get('error', '')}"
            )
            return None

        # Filter to substantive messages (skip joins, leaves, bot noise)
        substantive = [
            msg
            for msg in messages
            if msg.get("text", "").strip()
            and msg.get("subtype") not in (
                "channel_join",
                "channel_leave",
                "channel_topic",
                "channel_purpose",
                "bot_add",
                "bot_remove",
            )
        ]

        if len(substantive) < MIN_SUBSTANTIVE_MESSAGES:
            return None

        # Build a text block for the LLM
        message_texts = []
        for msg in substantive[:30]:  # Cap at 30 messages for the LLM
            text = msg.get("text", "").strip()
            if text:
                message_texts.append(text)

        combined = "\n---\n".join(message_texts)

        # Generate summary with LLM
        from app.core.llm import LLMMessage, get_llm_provider

        provider = get_llm_provider("gemini-2.5-flash")
        prompt = (
            f"Below are recent messages from a Slack channel called #{channel_name}. "
            "Write a 1-2 sentence summary of what this channel is primarily about. "
            "Focus on the topic/purpose, not specific people or messages.\n\n"
            f"{combined}"
        )

        try:
            summary = await provider.generate(
                [LLMMessage(role="user", content=prompt)]
            )
            return summary.strip() if summary else None
        except Exception as e:
            logger.error(f"LLM summary generation failed for #{channel_name}: {e}")
            return None


def _unix_to_datetime(ts: int | float) -> datetime | None:
    """Convert a Unix timestamp to datetime, or None if invalid/zero."""
    if not ts:
        return None
    try:
        return datetime.utcfromtimestamp(float(ts))
    except (ValueError, TypeError, OSError):
        return None
