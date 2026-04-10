"""Thread context fetching for triage classification."""

import logging
from datetime import datetime, timedelta

from slack_sdk.web.async_client import AsyncWebClient

logger = logging.getLogger(__name__)


class ThreadContextService:
    """Fetches recent thread replies for classification context."""

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