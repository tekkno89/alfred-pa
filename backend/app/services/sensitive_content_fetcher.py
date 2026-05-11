"""Fetcher for sensitive content that must be fetched on-demand from Slack.

Sensitive content (DMs, private channels, user-flagged channels) is never
cached in the database. This service provides a unified interface for
fetching such content with rate-limit handling.
"""

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING

from slack_sdk.errors import SlackApiError

if TYPE_CHECKING:
    from slack_sdk.web.async_client import AsyncWebClient

logger = logging.getLogger(__name__)


@dataclass
class FetchedMessage:
    """A message fetched from Slack API."""
    message_ts: str
    sender_slack_id: str
    text: str
    is_bot: bool
    created_at: datetime | None


class SensitiveContentFetcher:
    """Fetches sensitive content from Slack API with rate-limit handling.

    This service is used for:
    - DM conversation context
    - Private channel messages
    - User-flagged sensitive channels
    - Engagement checks on sensitive content
    - Escalation-time context fetch
    """

    def __init__(self, client: "AsyncWebClient") -> None:
        self.client = client

    async def fetch_message(
        self,
        channel_id: str,
        message_ts: str,
    ) -> FetchedMessage | None:
        """Fetch a single message from Slack.

        Returns None if message not found or rate-limited.
        """
        try:
            response = await self.client.conversations_history(
                channel=channel_id,
                latest=message_ts,
                limit=1,
                inclusive=True,
            )
            messages = response.get("messages", [])
            if not messages:
                return None

            msg = messages[0]
            return self._parse_message(msg)

        except SlackApiError as e:
            if e.response.get("error") == "ratelimited":
                logger.warning(
                    f"Rate limited fetching message {channel_id}/{message_ts}"
                )
                return None
            logger.exception(f"Slack API error fetching message: {e}")
            return None

    async def fetch_thread(
        self,
        channel_id: str,
        thread_ts: str,
        max_messages: int = 50,
    ) -> list[FetchedMessage]:
        """Fetch all messages in a thread.

        Returns empty list on failure (no fallback to cache).
        """
        try:
            response = await self.client.conversations_replies(
                channel=channel_id,
                ts=thread_ts,
                limit=max_messages,
            )
            messages = response.get("messages", [])
            return [self._parse_message(msg) for msg in messages]

        except SlackApiError as e:
            if e.response.get("error") == "ratelimited":
                logger.warning(
                    f"Rate limited fetching thread {channel_id}/{thread_ts}"
                )
            else:
                logger.exception(f"Slack API error fetching thread: {e}")
            return []

    async def fetch_dm_conversation(
        self,
        channel_id: str,
        max_messages: int = 20,
    ) -> list[FetchedMessage]:
        """Fetch recent DM conversation context.

        DMs are always fetched on-demand, never cached.
        """
        try:
            response = await self.client.conversations_history(
                channel=channel_id,
                limit=max_messages,
            )
            messages = response.get("messages", [])
            return [self._parse_message(msg) for msg in messages]

        except SlackApiError as e:
            if e.response.get("error") == "ratelimited":
                logger.warning(f"Rate limited fetching DM conversation {channel_id}")
            else:
                logger.exception(f"Slack API error fetching DM: {e}")
            return []

    async def check_engagement(
        self,
        channel_id: str,
        user_slack_id: str,
        after_ts: str,
        thread_ts: str | None = None,
    ) -> bool:
        """Check if user has engaged (reacted or replied) after a timestamp.

        Used for engagement checks on sensitive content.
        """
        try:
            if thread_ts:
                response = await self.client.conversations_replies(
                    channel=channel_id,
                    ts=thread_ts,
                    limit=100,
                )
            else:
                response = await self.client.conversations_history(
                    channel=channel_id,
                    limit=50,
                )

            messages = response.get("messages", [])

            for msg in messages:
                msg_ts = msg.get("ts", "0")
                if msg_ts <= after_ts:
                    continue

                if msg.get("user") == user_slack_id:
                    return True

                reactions = msg.get("reactions", [])
                for reaction in reactions:
                    if user_slack_id in reaction.get("users", []):
                        return True

            return False

        except SlackApiError as e:
            logger.warning(f"Failed to check engagement for {channel_id}: {e}")
            return False

    def _parse_message(self, msg: dict) -> FetchedMessage:
        """Parse a Slack message dict into FetchedMessage."""
        ts = msg.get("ts", "")
        created_at = None
        try:
            ts_float = float(ts)
            created_at = datetime.utcfromtimestamp(ts_float)
        except (ValueError, TypeError):
            pass

        return FetchedMessage(
            message_ts=ts,
            sender_slack_id=msg.get("user", msg.get("bot_id", "unknown")),
            text=msg.get("text", ""),
            is_bot=msg.get("bot_id") is not None,
            created_at=created_at,
        )
