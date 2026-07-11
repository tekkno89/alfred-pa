"""Slack channel client — picks the right token for reading channel content.

Use this instead of get_slack_service() when reading from channels/threads.
The bot token may not have access to all channels a user monitors.
The user's OAuth token always has access to their channels.

Usage:
    from app.services.slack_channel_client import SlackChannelClient

    client = await SlackChannelClient.for_user(db, user_id)
    result = await client.conversations_history(channel=channel_id, limit=10)

When to use which:
    - SlackChannelClient.for_user()  → reading channel/thread content
    - get_slack_service()            → sending messages, reactions (bot actions)
"""

import logging

from slack_sdk.web.async_client import AsyncWebClient
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


class SlackChannelClient:
    """Factory for Slack clients that can read channel content.

    Resolves the user's OAuth token for reading channels the bot
    may not be a member of. Falls back to bot token if user token
    is unavailable.
    """

    @classmethod
    async def for_user(cls, db: AsyncSession, user_id: str) -> AsyncWebClient:
        """Get a Slack client using the user's OAuth token.

        Args:
            db: Database session for token lookup
            user_id: Alfred user ID

        Returns:
            AsyncWebClient configured with the user's token,
            or bot token as fallback.
        """
        from app.services.slack_user import SlackUserService

        service = SlackUserService(db)
        client = await service._get_user_client(user_id)
        if client:
            return client

        logger.warning(
            f"No user OAuth token for user {user_id}, "
            f"falling back to bot token (may fail for some channels)"
        )
        from app.services.slack import get_slack_service

        return get_slack_service().client
