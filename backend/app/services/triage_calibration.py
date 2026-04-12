"""Triage calibration service — sample Slack messages for priority calibration."""

import logging
import random
from typing import Any

from slack_sdk.errors import SlackApiError
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.slack import fetch_user_channels
from app.services.slack_user import SlackUserService

logger = logging.getLogger(__name__)


class TriageCalibrationService:
    """Samples and manages real Slack messages for priority calibration."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def sample_user_messages(
        self, user_id: str, target_count: int = 10
    ) -> list[dict[str, Any]]:
        """
        Sample recent messages from user's Slack channels for calibration.

        Samples from:
        - 1-2 DM channels
        - 2-3 public channels
        - 2-3 private channels (if available)

        Args:
            user_id: User ID
            target_count: Target number of messages to sample (default 10)

        Returns:
            List of message dicts with keys:
            - message_text, sender_name, channel_name, channel_type
            - message_ts, channel_id, permalink
        """
        # Get user's Slack token
        user_svc = SlackUserService(self.db)
        user_token = await user_svc.get_raw_token(user_id)

        if not user_token:
            raise ValueError("User has no Slack token connected")

        # Fetch channels user belongs to
        try:
            channels = await fetch_user_channels(user_token)
        except SlackApiError as e:
            logger.error(f"Failed to fetch user channels: {e.response['error']}")
            raise

        # Categorize channels by type
        public_channels = [ch for ch in channels if not ch.get("is_private")]
        private_channels = [ch for ch in channels if ch.get("is_private")]

        # Note: DM channels are harder to identify from users.conversations
        # We'll sample from public/private channels for now

        messages: list[dict[str, Any]] = []

        # Sample from public channels (2-3)
        if public_channels:
            sampled_public = random.sample(
                public_channels, min(3, len(public_channels))
            )
            for ch in sampled_public:
                ch_messages = await self._fetch_channel_messages(
                    user_token, ch["id"], ch.get("name", "unknown"), "public", limit=2
                )
                messages.extend(ch_messages)

        # Sample from private channels (2-3)
        if private_channels:
            sampled_private = random.sample(
                private_channels, min(3, len(private_channels))
            )
            for ch in sampled_private:
                ch_messages = await self._fetch_channel_messages(
                    user_token, ch["id"], ch.get("name", "unknown"), "private", limit=2
                )
                messages.extend(ch_messages)

        # Shuffle and return up to target_count
        random.shuffle(messages)
        return messages[:target_count]

    async def _fetch_channel_messages(
        self,
        token: str,
        channel_id: str,
        channel_name: str,
        channel_type: str,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        """
        Fetch recent messages from a Slack channel.

        Args:
            token: User's Slack token
            channel_id: Channel ID
            channel_name: Channel name for display
            channel_type: "public", "private", or "dm"
            limit: Max messages to fetch

        Returns:
            List of formatted message dicts
        """
        from slack_sdk.web.async_client import AsyncWebClient

        client = AsyncWebClient(token=token)
        messages = []

        try:
            response = await client.conversations_history(
                channel=channel_id, limit=limit
            )

            for msg in response.get("messages", []):
                # Skip bot messages and very short messages
                if msg.get("bot_id") or msg.get("subtype"):
                    continue

                text = msg.get("text", "")
                if len(text) < 10:  # Skip very short messages
                    continue

                # Get sender info
                sender_id = msg.get("user", "Unknown")
                sender_name = await self._get_user_display_name(client, sender_id)

                # Get permalink
                try:
                    permalink_response = await client.chat_getPermalink(
                        channel=channel_id, message_ts=msg["ts"]
                    )
                    permalink = permalink_response.get("permalink", "")
                except SlackApiError:
                    permalink = ""

                messages.append(
                    {
                        "message_text": text[:500],  # Truncate long messages
                        "sender_name": sender_name,
                        "sender_slack_id": sender_id,
                        "channel_name": channel_name,
                        "channel_type": channel_type,
                        "message_ts": msg["ts"],
                        "channel_id": channel_id,
                        "permalink": permalink,
                    }
                )

                if len(messages) >= limit:
                    break

        except SlackApiError as e:
            logger.warning(
                f"Failed to fetch messages from {channel_name}: {e.response['error']}"
            )

        return messages

    async def _get_user_display_name(
        self, client, user_id: str
    ) -> str:
        """Get display name for a Slack user."""
        try:
            response = await client.users_info(user=user_id)
            user = response.get("user", {})
            # Prefer display_name, fall back to real_name, then name
            profile = user.get("profile", {})
            return (
                profile.get("display_name")
                or profile.get("real_name")
                or user.get("name")
                or user_id
            )
        except SlackApiError:
            return user_id

    def check_priority_coverage(
        self, ratings: list[dict[str, Any]]
    ) -> set[str]:
        """
        Check which priority levels have been rated.

        Args:
            ratings: List of rating dicts with 'priority' key

        Returns:
            Set of missing priority levels (subset of {'p0', 'p1', 'p2', 'p3'})
        """
        rated_priorities = {r.get("priority") for r in ratings}
        all_priorities = {"p0", "p1", "p2", "p3"}
        return all_priorities - rated_priorities

    def format_message_for_review(self, message: dict[str, Any]) -> str:
        """
        Format a message for UI display in calibration.

        Args:
            message: Message dict with text, sender, channel info

        Returns:
            Formatted string for display
        """
        sender = message.get("sender_name", "Unknown")
        channel = message.get("channel_name", "unknown")
        channel_type = message.get("channel_type", "public")
        text = message.get("message_text", "")

        # Truncate to ~200 chars for display
        display_text = text[:200] + "..." if len(text) > 200 else text

        channel_indicator = (
            "🔒" if channel_type == "private"
            else "💬" if channel_type == "dm"
            else "#"
        )

        return f"{channel_indicator} {channel} | {sender}: {display_text}"