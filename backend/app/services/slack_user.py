"""Slack user service for user-token operations (status, presence)."""

import logging
from datetime import datetime
from typing import Any

from slack_sdk.web.async_client import AsyncWebClient
from slack_sdk.errors import SlackApiError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.repositories import OAuthTokenRepository

logger = logging.getLogger(__name__)


class SlackUserService:
    """Service for Slack operations using user OAuth tokens."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.token_repo = OAuthTokenRepository(db)

    async def _get_user_client(self, user_id: str) -> AsyncWebClient | None:
        """Get a Slack client using the user's OAuth token."""
        token = await self.token_repo.get_by_user_and_provider(user_id, "slack")
        if not token:
            return None
        return AsyncWebClient(token=token.access_token)

    async def has_oauth_token(self, user_id: str) -> bool:
        """Check if user has a Slack OAuth token."""
        token = await self.token_repo.get_by_user_and_provider(user_id, "slack")
        return token is not None

    async def get_status(self, user_id: str) -> dict[str, Any] | None:
        """
        Get user's current Slack status.

        Args:
            user_id: The user's ID

        Returns:
            Status dict with text, emoji, expiration or None if no token
        """
        client = await self._get_user_client(user_id)
        if not client:
            return None

        try:
            response = await client.users_profile_get()
            profile = response.get("profile", {})
            return {
                "text": profile.get("status_text", ""),
                "emoji": profile.get("status_emoji", ""),
                "expiration": profile.get("status_expiration", 0),
            }
        except SlackApiError as e:
            logger.error(f"Error getting Slack status: {e.response['error']}")
            return None

    async def set_status(
        self,
        user_id: str,
        text: str,
        emoji: str = ":no_bell:",
        expiration: int = 0,
    ) -> bool:
        """
        Set user's Slack status.

        Args:
            user_id: The user's ID
            text: Status text
            emoji: Status emoji (default: :no_bell:)
            expiration: Unix timestamp when status expires (0 = never)

        Returns:
            True if successful, False otherwise
        """
        client = await self._get_user_client(user_id)
        if not client:
            logger.warning(f"No Slack OAuth token for user {user_id}")
            return False

        try:
            await client.users_profile_set(
                profile={
                    "status_text": text,
                    "status_emoji": emoji,
                    "status_expiration": expiration,
                }
            )
            return True
        except SlackApiError as e:
            logger.error(f"Error setting Slack status: {e.response['error']}")
            return False

    async def set_presence(self, user_id: str, presence: str) -> bool:
        """
        Set user's Slack presence.

        Args:
            user_id: The user's ID
            presence: 'auto' or 'away'

        Returns:
            True if successful, False otherwise
        """
        client = await self._get_user_client(user_id)
        if not client:
            logger.warning(f"No Slack OAuth token for user {user_id}")
            return False

        try:
            await client.users_setPresence(presence=presence)
            return True
        except SlackApiError as e:
            logger.error(f"Error setting Slack presence: {e.response['error']}")
            return False

    async def enable_dnd(self, user_id: str, duration_minutes: int = 60) -> bool:
        """
        Enable Do Not Disturb mode for a user.

        Args:
            user_id: The user's ID
            duration_minutes: How long to snooze notifications (default: 60 min)

        Returns:
            True if successful, False otherwise
        """
        client = await self._get_user_client(user_id)
        if not client:
            logger.warning(f"No Slack OAuth token for user {user_id}")
            return False

        try:
            await client.dnd_setSnooze(num_minutes=duration_minutes)
            return True
        except SlackApiError as e:
            logger.error(f"Error enabling Slack DND: {e.response['error']}")
            return False

    async def disable_dnd(self, user_id: str) -> bool:
        """
        Disable Do Not Disturb mode for a user.

        Args:
            user_id: The user's ID

        Returns:
            True if successful, False otherwise
        """
        client = await self._get_user_client(user_id)
        if not client:
            logger.warning(f"No Slack OAuth token for user {user_id}")
            return False

        try:
            await client.dnd_endSnooze()
            return True
        except SlackApiError as e:
            # "snooze_not_active" is not really an error
            if e.response.get("error") == "snooze_not_active":
                return True
            logger.error(f"Error disabling Slack DND: {e.response['error']}")
            return False

    async def store_token(
        self,
        user_id: str,
        access_token: str,
        refresh_token: str | None = None,
        scope: str | None = None,
        expires_at: datetime | None = None,
    ) -> None:
        """Store a Slack OAuth token for a user."""
        await self.token_repo.upsert(
            user_id=user_id,
            provider="slack",
            access_token=access_token,
            refresh_token=refresh_token,
            scope=scope,
            expires_at=expires_at,
        )

    async def revoke_token(self, user_id: str) -> bool:
        """Revoke and delete a user's Slack OAuth token."""
        token = await self.token_repo.get_by_user_and_provider(user_id, "slack")
        if not token:
            return False

        # Try to revoke the token with Slack
        client = AsyncWebClient(token=token.access_token)
        try:
            await client.auth_revoke()
        except SlackApiError as e:
            logger.warning(f"Error revoking Slack token: {e.response['error']}")
            # Continue to delete even if revocation fails

        # Delete from database
        return await self.token_repo.delete_by_user_and_provider(user_id, "slack")
