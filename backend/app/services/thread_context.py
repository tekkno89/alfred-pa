"""Thread and DM context fetching for triage classification."""

import logging
from datetime import datetime, timedelta

from slack_sdk.web.async_client import AsyncWebClient

logger = logging.getLogger(__name__)


class ThreadContextService:
    """Fetches recent thread replies or DM conversation history for classification context."""

    def __init__(self, client: AsyncWebClient):
        self.client = client

    async def get_thread_context(
        self,
        channel_id: str,
        thread_ts: str,
        max_replies: int = 10,
    ) -> str:
        """
        Fetch up to last 10 thread replies as context.

        Returns a formatted string with recent thread messages (not raw messages).
        Format: "Recent thread: [<@user1>: summary...] [<@user2>: summary...]"

        Args:
            channel_id: Slack channel ID
            thread_ts: Thread timestamp (parent message ts)
            max_replies: Maximum number of replies to fetch (default 10)

        Returns:
            Formatted thread context string, or empty string if no replies
        """
        if not thread_ts:
            return ""

        try:
            # Fetch thread replies
            response = await self.client.conversations_replies(
                channel=channel_id,
                ts=thread_ts,
                limit=max_replies,
            )

            messages = response.get("messages", [])
            if len(messages) <= 1:  # Only parent message, no replies
                return ""

            # Build context summary (not raw text)
            context_parts = []
            # Skip parent message (first message), process replies only
            for msg in messages[1:]:
                user_id = msg.get("user", "")
                text = msg.get("text", "")
                # Summarize each reply briefly (preserve privacy)
                summary = self._summarize_for_context(text, max_length=100)
                if summary:
                    context_parts.append(f"<@{user_id}>: {summary}")

            if not context_parts:
                return ""

            return f"Recent thread context: {' | '.join(context_parts)}"

        except Exception as e:
            logger.warning(f"Failed to fetch thread context for {thread_ts}: {e}")
            return ""

    async def get_dm_conversation_context(
        self,
        channel_id: str,
        max_messages: int = 10,
    ) -> str:
        """
        Fetch recent DM conversation history as context.

        Returns a formatted string with recent DM messages (not raw messages).
        Format: "Recent DM conversation: [<@user1>: summary...] [<@user2>: summary...]"

        Args:
            channel_id: Slack DM channel ID (starts with 'D')
            max_messages: Maximum number of recent messages to fetch (default 10)

        Returns:
            Formatted DM conversation context string, or empty string if no messages
        """
        try:
            # Fetch recent DM conversation history
            response = await self.client.conversations_history(
                channel=channel_id,
                limit=max_messages,
            )

            messages = response.get("messages", [])
            if not messages:
                return ""

            # Build context summary (not raw text)
            context_parts = []
            # Process messages in chronological order (oldest first)
            for msg in reversed(messages):
                user_id = msg.get("user", "")
                text = msg.get("text", "")
                ts = msg.get("ts", "")

                # Skip empty messages or bot messages
                if not text or msg.get("bot_id"):
                    continue

                # Calculate message age
                if ts:
                    try:
                        msg_time = datetime.fromtimestamp(float(ts))
                        age_hours = (datetime.utcnow() - msg_time).total_seconds() / 3600
                        age_str = self._format_age(age_hours)
                    except (ValueError, OSError):
                        age_str = ""
                else:
                    age_str = ""

                # Summarize each message briefly
                summary = self._summarize_for_context(text, max_length=100)
                if summary:
                    age_label = f" ({age_str})" if age_str else ""
                    context_parts.append(f"<@{user_id}>{age_label}: {summary}")

            if not context_parts:
                return ""

            return f"Recent DM conversation (last {len(context_parts)} messages): {' | '.join(context_parts)}"

        except Exception as e:
            logger.warning(f"Failed to fetch DM conversation context for {channel_id}: {e}")
            return ""

    def _format_age(self, age_hours: float) -> str:
        """
        Format message age in human-readable format.

        Args:
            age_hours: Age in hours

        Returns:
            Human-readable age string (e.g., "2h ago", "3d ago")
        """
        if age_hours < 1:
            return "just now"
        elif age_hours < 24:
            return f"{int(age_hours)}h ago"
        else:
            days = int(age_hours / 24)
            return f"{days}d ago"

    def _summarize_for_context(self, text: str, max_length: int = 100) -> str:
        """
        Create a brief summary of message for context (no raw quoting).

        Args:
            text: Message text
            max_length: Maximum length for summary

        Returns:
            Truncated summary string
        """
        text = text.strip()
        if not text:
            return ""

        # Simple truncation for now
        # Can enhance with LLM summarization in future if needed
        if len(text) <= max_length:
            return text
        return text[: max_length - 3] + "..."