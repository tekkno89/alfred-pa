"""Triage calibration service — sample Slack messages for priority calibration."""

import logging
import random
import re
from typing import Any

from slack_sdk.errors import SlackApiError
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.slack import fetch_user_channels
from app.services.slack_user import SlackUserService

logger = logging.getLogger(__name__)


def parse_slack_permalink(permalink: str) -> dict[str, str] | None:
    """
    Parse a Slack permalink to extract channel_id and message_ts.

    Formats:
    - https://workspace.slack.com/archives/C12345/p1234567890123456
    - https://workspace.slack.com/archives/C12345/p1234567890123456?thread_ts=1234567890123456&cid=C12345

    Args:
        permalink: Slack message permalink URL

    Returns:
        Dict with 'channel_id', 'message_ts', and optionally 'thread_ts', or None if invalid
    """
    pattern = r"https?://[\w-]+\.slack\.com/archives/([A-Z0-9]+)/p(\d+)"
    match = re.match(pattern, permalink)

    if not match:
        return None

    channel_id = match.group(1)
    ts_digits = match.group(2)

    if len(ts_digits) < 10:
        return None

    message_ts = f"{ts_digits[:10]}.{ts_digits[10:]}"

    result: dict[str, str] = {
        "channel_id": channel_id,
        "message_ts": message_ts,
    }

    thread_match = re.search(r"thread_ts=(\d+)", permalink)
    if thread_match:
        thread_digits = thread_match.group(1)
        if len(thread_digits) >= 10:
            result["thread_ts"] = f"{thread_digits[:10]}.{thread_digits[10:]}"

    return result


class TriageCalibrationService:
    """Samples and manages real Slack messages for priority calibration."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def sample_user_messages(
        self,
        user_id: str,
        exclude_message_ids: list[str] | None = None,
        target_count: int = 10,
        max_per_channel: int = 2,
    ) -> list[dict[str, Any]]:
        """
        Sample recent messages from user's Slack channels for calibration.

        Distributes messages across multiple channels for diversity:
        - Max 2 messages per channel by default
        - Samples from DMs, public channels, and private channels
        - Randomizes channel order for variety

        Args:
            user_id: User ID
            exclude_message_ids: List of message IDs to exclude (format: "channel_id:ts")
            target_count: Target number of messages to sample (default 10)
            max_per_channel: Max messages to take from any single channel (default 2)

        Returns:
            List of message dicts with keys:
            - message_id, message_text, sender_name, channel_name, channel_type
            - message_ts, channel_id, permalink
        """
        if exclude_message_ids is None:
            exclude_message_ids = []

        user_svc = SlackUserService(self.db)
        user_token = await user_svc.get_raw_token(user_id)

        if not user_token:
            raise ValueError("User has no Slack token connected")

        try:
            channels = await fetch_user_channels(user_token)
        except SlackApiError as e:
            logger.error(f"Failed to fetch user channels: {e.response['error']}")
            raise

        public_channels = [
            ch for ch in channels if not ch.get("is_private") and not ch.get("is_im")
        ]
        private_channels = [ch for ch in channels if ch.get("is_private")]
        dm_channels = [ch for ch in channels if ch.get("is_im")]

        random.shuffle(public_channels)
        random.shuffle(private_channels)
        random.shuffle(dm_channels)

        all_channels = []
        all_channels.extend([("dm", ch) for ch in dm_channels[:3]])
        all_channels.extend([("public", ch) for ch in public_channels[:5]])
        all_channels.extend([("private", ch) for ch in private_channels[:5]])
        random.shuffle(all_channels)

        messages: list[dict[str, Any]] = []
        collected_ids: set[str] = set(exclude_message_ids)
        collected_content: set[str] = set()

        for channel_type, ch in all_channels:
            if len(messages) >= target_count:
                break

            ch_messages = await self._fetch_channel_messages(
                user_token,
                ch["id"],
                ch.get("name", "unknown"),
                channel_type,
                limit=5,
                exclude_message_ids=list(collected_ids),
            )

            added_from_channel = 0
            for msg in ch_messages:
                if len(messages) >= target_count:
                    break
                if added_from_channel >= max_per_channel:
                    break

                if msg["message_id"] not in collected_ids:
                    content_key = msg["message_text"][:100].lower().strip()

                    if content_key not in collected_content:
                        messages.append(msg)
                        collected_ids.add(msg["message_id"])
                        collected_content.add(content_key)
                        added_from_channel += 1
                        logger.info(
                            f"Added message from {ch.get('name', 'unknown')}: {msg['message_text'][:50]}..."
                        )

        random.shuffle(messages)
        return messages[:target_count]

    async def _fetch_channel_messages(
        self,
        token: str,
        channel_id: str,
        channel_name: str,
        channel_type: str,
        limit: int = 5,
        exclude_message_ids: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """
        Fetch recent messages from a Slack channel.

        Args:
            token: User's Slack token
            channel_id: Channel ID
            channel_name: Channel name for display
            channel_type: "public", "private", or "dm"
            limit: Max messages to fetch
            exclude_message_ids: List of message IDs to exclude (format: "channel_id:ts")

        Returns:
            List of formatted message dicts
        """
        if exclude_message_ids is None:
            exclude_message_ids = []

        from slack_sdk.web.async_client import AsyncWebClient

        client = AsyncWebClient(token=token)
        messages = []

        try:
            response = await client.conversations_history(
                channel=channel_id,
                limit=limit * 2,  # Fetch extra to account for exclusions
            )

            for msg in response.get("messages", []):
                # Skip bot messages and very short messages
                if msg.get("bot_id") or msg.get("subtype"):
                    continue

                text = msg.get("text", "")
                if len(text) < 10:  # Skip very short messages
                    continue

                # Create unique message ID
                message_ts = msg["ts"]
                message_id = f"{channel_id}:{message_ts}"

                # Skip if this message was already shown
                if message_id in exclude_message_ids:
                    continue

                # Get sender info
                sender_id = msg.get("user", "Unknown")
                sender_name = await self._get_user_display_name(client, sender_id)

                # Get permalink
                try:
                    permalink_response = await client.chat_getPermalink(
                        channel=channel_id, message_ts=message_ts
                    )
                    permalink = permalink_response.get("permalink", "")
                except SlackApiError:
                    permalink = ""

                messages.append(
                    {
                        "message_id": message_id,
                        "message_text": text[:500],  # Truncate long messages
                        "sender_name": sender_name,
                        "sender_slack_id": sender_id,
                        "channel_name": channel_name,
                        "channel_type": channel_type,
                        "message_ts": message_ts,
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

    async def _get_user_display_name(self, client, user_id: str) -> str:
        """Get display name for a Slack user."""
        try:
            response = await client.users_info(user=user_id)
            user = response.get("user", {})
            profile = user.get("profile", {})
            return (
                profile.get("display_name")
                or profile.get("real_name")
                or user.get("name")
                or user_id
            )
        except SlackApiError:
            return user_id

    async def fetch_message_by_permalink(
        self, user_id: str, permalink: str
    ) -> dict[str, Any] | None:
        """
        Fetch a specific Slack message by its permalink.

        Args:
            user_id: User ID
            permalink: Slack message permalink URL

        Returns:
            Message dict with same format as sample_user_messages, or None if not found
        """
        parsed = parse_slack_permalink(permalink)
        if not parsed:
            logger.warning(f"Invalid permalink format: {permalink}")
            return None

        user_svc = SlackUserService(self.db)
        user_token = await user_svc.get_raw_token(user_id)

        if not user_token:
            raise ValueError("User has no Slack token connected")

        from slack_sdk.web.async_client import AsyncWebClient

        client = AsyncWebClient(token=user_token)
        channel_id = parsed["channel_id"]
        message_ts = parsed["message_ts"]
        thread_ts = parsed.get("thread_ts")

        try:
            channel_info = await client.conversations_info(channel=channel_id)
            channel_data = channel_info.get("channel", {})
            channel_name = channel_data.get("name", "unknown")
            is_private = channel_data.get("is_private", False)
            is_im = channel_data.get("is_im", False)

            if is_im:
                channel_type = "dm"
            elif is_private:
                channel_type = "private"
            else:
                channel_type = "public"

            if thread_ts:
                response = await client.conversations_replies(
                    channel=channel_id,
                    ts=thread_ts,
                    limit=100,
                )
                messages_list = response.get("messages", [])
                target_msg = None
                for msg in messages_list:
                    if msg.get("ts") == message_ts:
                        target_msg = msg
                        break
            else:
                response = await client.conversations_history(
                    channel=channel_id,
                    latest=message_ts,
                    inclusive=True,
                    limit=1,
                )
                messages_list = response.get("messages", [])
                target_msg = messages_list[0] if messages_list else None

            if not target_msg:
                logger.warning(f"Message not found: {permalink}")
                return None

            if target_msg.get("bot_id") or target_msg.get("subtype"):
                logger.warning(f"Skipping bot/subtype message: {permalink}")
                return None

            text = target_msg.get("text", "")
            if len(text) < 10:
                logger.warning(f"Message too short: {permalink}")
                return None

            sender_id = target_msg.get("user", "Unknown")
            sender_name = await self._get_user_display_name(client, sender_id)

            return {
                "message_id": f"{channel_id}:{message_ts}",
                "message_text": text[:500],
                "sender_name": sender_name,
                "sender_slack_id": sender_id,
                "channel_name": channel_name,
                "channel_type": channel_type,
                "message_ts": message_ts,
                "channel_id": channel_id,
                "permalink": permalink,
            }

        except SlackApiError as e:
            logger.error(f"Failed to fetch message by permalink: {e.response['error']}")
            return None

    def check_priority_coverage(self, ratings: list[dict[str, Any]]) -> set[str]:
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
            "🔒" if channel_type == "private" else "💬" if channel_type == "dm" else "#"
        )

        return f"{channel_indicator} {channel} | {sender}: {display_text}"
