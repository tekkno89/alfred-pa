"""Slack service for API interactions."""

import hashlib
import hmac
import logging
import time
from typing import Any

from fastapi import Request
from slack_sdk.web.async_client import AsyncWebClient
from slack_sdk.errors import SlackApiError

from app.core.config import get_settings

logger = logging.getLogger(__name__)


class SlackService:
    """Service for Slack API interactions."""

    def __init__(self):
        settings = get_settings()
        self.client = AsyncWebClient(token=settings.slack_bot_token)
        self.signing_secret = settings.slack_signing_secret
        self._bot_user_id: str | None = None

    async def get_bot_user_id(self) -> str | None:
        """Get the bot's Slack user ID (cached after first call)."""
        if self._bot_user_id is None:
            try:
                response = await self.client.auth_test()
                self._bot_user_id = response.data.get("user_id")
            except SlackApiError as e:
                logger.error(f"Error getting bot user ID: {e.response['error']}")
        return self._bot_user_id

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


# Singleton instance
_slack_service: SlackService | None = None


def get_slack_service() -> SlackService:
    """Get or create SlackService singleton."""
    global _slack_service
    if _slack_service is None:
        _slack_service = SlackService()
    return _slack_service
