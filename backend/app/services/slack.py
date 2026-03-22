"""Slack service for API interactions."""

import asyncio
import hashlib
import hmac
import logging
import time
from typing import Any

from slack_sdk.errors import SlackApiError
from slack_sdk.web.async_client import AsyncWebClient

from app.core.config import get_settings

logger = logging.getLogger(__name__)


class SlackService:
    """Service for Slack API interactions."""

    def __init__(self):
        settings = get_settings()
        self.client = AsyncWebClient(token=settings.slack_bot_token)
        self.signing_secret = settings.slack_signing_secret
        # Cache of channel IDs confirmed as bot DM channels
        self._bot_dm_channels: set[str] = set()

    async def is_bot_dm_channel(self, channel_id: str) -> bool:
        """
        Check if a DM channel is between the bot and a user.

        Uses conversations.info with the bot token — the bot can only see
        DM channels it participates in. Results are cached in-memory.
        """
        if channel_id in self._bot_dm_channels:
            return True

        try:
            await self.client.conversations_info(channel=channel_id)
            self._bot_dm_channels.add(channel_id)
            return True
        except SlackApiError:
            return False

    async def verify_signature(
        self,
        body: bytes,
        timestamp: str,
        signature: str,
    ) -> bool:
        """
        Verify Slack request signature.

        Args:
            body: Raw request body
            timestamp: X-Slack-Request-Timestamp header
            signature: X-Slack-Signature header

        Returns:
            True if signature is valid, False otherwise
        """
        if not self.signing_secret:
            logger.warning("Slack signing secret not configured")
            return False

        # Check timestamp to prevent replay attacks (5 minutes tolerance)
        try:
            request_time = int(timestamp)
            current_time = int(time.time())
            if abs(current_time - request_time) > 60 * 5:
                logger.warning("Slack request timestamp too old")
                return False
        except ValueError:
            logger.warning("Invalid Slack timestamp")
            return False

        # Compute signature
        sig_basestring = f"v0:{timestamp}:{body.decode('utf-8')}"
        computed_signature = (
            "v0="
            + hmac.new(
                self.signing_secret.encode("utf-8"),
                sig_basestring.encode("utf-8"),
                hashlib.sha256,
            ).hexdigest()
        )

        # Compare signatures (timing-safe)
        return hmac.compare_digest(computed_signature, signature)

    async def send_message(
        self,
        channel: str,
        text: str,
        thread_ts: str | None = None,
    ) -> dict[str, Any]:
        """
        Send a message to Slack channel/thread.

        Args:
            channel: Channel ID to send to
            text: Message text
            thread_ts: Thread timestamp for threading replies

        Returns:
            Slack API response
        """
        try:
            response = await self.client.chat_postMessage(
                channel=channel,
                text=text,
                thread_ts=thread_ts,
            )
            return response.data
        except SlackApiError as e:
            logger.error(f"Error sending Slack message: {e.response['error']}")
            raise

    async def add_reaction(
        self,
        channel: str,
        timestamp: str,
        name: str = "thinking_face",
    ) -> bool:
        """
        Add an emoji reaction to a message.

        Returns True on success (or if already reacted), False on failure.
        Never raises — callers should not fail if reactions fail.
        """
        try:
            await self.client.reactions_add(
                channel=channel, timestamp=timestamp, name=name
            )
            return True
        except SlackApiError as e:
            error = e.response.get("error", "")
            if error == "already_reacted":
                return True
            logger.warning(f"Could not add reaction '{name}': {error}")
            return False

    async def remove_reaction(
        self,
        channel: str,
        timestamp: str,
        name: str = "thinking_face",
    ) -> bool:
        """
        Remove an emoji reaction from a message.

        Returns True on success (or if no reaction existed), False on failure.
        Never raises — callers should not fail if reactions fail.
        """
        try:
            await self.client.reactions_remove(
                channel=channel, timestamp=timestamp, name=name
            )
            return True
        except SlackApiError as e:
            error = e.response.get("error", "")
            if error == "no_reaction":
                return True
            logger.warning(f"Could not remove reaction '{name}': {error}")
            return False

    async def get_user_info(self, slack_user_id: str) -> dict[str, Any]:
        """
        Get Slack user profile info.

        Args:
            slack_user_id: Slack user ID

        Returns:
            User profile data
        """
        try:
            response = await self.client.users_info(user=slack_user_id)
            return response.data.get("user", {})
        except SlackApiError as e:
            logger.error(f"Error getting Slack user info: {e.response['error']}")
            raise


async def fetch_all_slack_channels(
    max_retries: int = 5,
    token: str | None = None,
) -> list[dict]:
    """Fetch all Slack channels with pagination and rate-limit retry.

    Tries public+private channels first; falls back to public-only if the
    token lacks the ``groups:read`` scope.

    Args:
        max_retries: Number of rate-limit retries per page.
        token: Slack token to use. When a user OAuth token is supplied the
            response includes all channels the *user* belongs to (including
            private channels). Falls back to the bot token when ``None``.

    Returns a list of dicts with keys: id, name, is_private, num_members.
    """
    if token is None:
        settings = get_settings()
        token = settings.slack_bot_token
    client = AsyncWebClient(token=token)

    channel_types = "public_channel,private_channel"
    try:
        return await _paginate_conversations(client, channel_types, max_retries)
    except SlackApiError as e:
        if e.response.get("error") == "missing_scope":
            needed = e.response.get("needed", "")
            logger.warning(
                f"Slack missing scope '{needed}', falling back to public channels only. "
                "Reinstall the Slack app to grant the missing scope."
            )
            return await _paginate_conversations(
                client, "public_channel", max_retries
            )
        raise


async def _paginate_conversations(
    client: AsyncWebClient,
    channel_types: str,
    max_retries: int,
) -> list[dict]:
    """Paginate through conversations.list with rate-limit retry."""
    raw_channels: list[dict] = []
    cursor = None
    while True:
        for attempt in range(max_retries + 1):
            try:
                response = await client.conversations_list(
                    types=channel_types,
                    exclude_archived=True,
                    limit=200,
                    cursor=cursor,
                )
                break
            except SlackApiError as e:
                if e.response.get("error") != "ratelimited" or attempt == max_retries:
                    raise
                retry_after = int(e.response.headers.get("Retry-After", 3))
                logger.warning(
                    f"Slack rate limited, retrying in {retry_after}s "
                    f"(attempt {attempt + 1}/{max_retries})"
                )
                await asyncio.sleep(retry_after)

        for ch in response.get("channels", []):
            raw_channels.append(
                {
                    "id": ch["id"],
                    "name": ch.get("name", ""),
                    "is_private": ch.get("is_private", False),
                    "num_members": ch.get("num_members", 0),
                }
            )
        cursor = response.get("response_metadata", {}).get("next_cursor")
        if not cursor:
            break
    return raw_channels


# Singleton instance
_slack_service: SlackService | None = None


def get_slack_service() -> SlackService:
    """Get or create SlackService singleton."""
    global _slack_service
    if _slack_service is None:
        _slack_service = SlackService()
    return _slack_service
