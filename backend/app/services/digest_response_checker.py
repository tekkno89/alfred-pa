"""Digest response checker — detect if user has responded to messages."""

import logging

from slack_sdk.web.async_client import AsyncWebClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.triage import TriageClassification
from app.db.repositories import OAuthTokenRepository
from app.services.digest_grouper import ConversationGroup
from app.services.token_encryption import TokenEncryptionService

logger = logging.getLogger(__name__)


class DigestResponseChecker:
    """Checks if the user has responded to messages or conversations.

    Uses the user's OAuth token (not the bot token) to check message history,
    since users are members of their monitored channels but the bot may not be.
    """

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.token_repo = OAuthTokenRepository(db)
        self.token_encryption = TokenEncryptionService(db)
        self._user_clients: dict[str, AsyncWebClient] = {}

    async def _get_user_client(self, user_id: str) -> AsyncWebClient | None:
        """Get a Slack client using the user's OAuth token.

        Caches the client for the lifetime of the checker instance.
        """
        if user_id in self._user_clients:
            return self._user_clients[user_id]

        token = await self.token_repo.get_by_user_and_provider(user_id, "slack")
        if not token:
            logger.warning(f"No Slack OAuth token for user {user_id}")
            return None

        access_token = await self.token_encryption.get_decrypted_access_token(token)
        if not access_token:
            logger.warning(f"Failed to decrypt Slack token for user {user_id}")
            return None

        client = AsyncWebClient(token=access_token)
        self._user_clients[user_id] = client
        return client

    async def filter_unresponded_conversations(
        self,
        user_id: str,
        user_slack_id: str,
        conversations: list[ConversationGroup],
    ) -> list[ConversationGroup]:
        """
        Filter out conversations the user has already responded to.

        A user has responded to a conversation if:
        1. They posted a message after the last message in the conversation

        Args:
            user_id: Alfred user ID
            user_slack_id: User's Slack ID
            conversations: List of ConversationGroup objects

        Returns:
            List of ConversationGroup objects the user has NOT responded to
        """
        unresponded = []

        for conv in conversations:
            user_responded = await self._check_user_message_response(
                user_id, user_slack_id, conv
            )
            if user_responded:
                logger.info(
                    f"Skipping conversation {conv.id}: user posted message after"
                )
                continue

            unresponded.append(conv)

        logger.info(
            f"Filtered {len(conversations)} conversations to {len(unresponded)} unresponded"
        )
        return unresponded

    async def _check_user_message_response(
        self, user_id: str, user_slack_id: str, conversation: ConversationGroup
    ) -> bool:
        """
        Check if user posted a message after the last message in the conversation.

        Args:
            user_id: Alfred user ID (for token lookup)
            user_slack_id: User's Slack ID
            conversation: ConversationGroup to check

        Returns:
            True if user posted after the conversation, False otherwise
        """
        client = await self._get_user_client(user_id)
        if not client:
            logger.warning(
                f"No user client for {user_id}, cannot check response for {conversation.id}"
            )
            return False

        try:
            if conversation.conversation_type == "thread":
                response = await client.conversations_replies(
                    channel=conversation.channel_id,
                    ts=conversation.thread_ts,
                    limit=50,
                )
            else:
                response = await client.conversations_history(
                    channel=conversation.channel_id,
                    limit=20,
                )

            messages = response.get("messages", [])
            last_conv_ts = conversation.last_message_ts

            for msg in messages:
                msg_ts = msg.get("ts", "0")
                msg_user = msg.get("user")

                if msg.get("bot_id") or msg.get("subtype") == "bot_message":
                    continue

                if msg_user == user_slack_id and msg_ts > last_conv_ts:
                    logger.debug(
                        f"User {user_slack_id} posted message {msg_ts} after "
                        f"conversation last message {last_conv_ts}"
                    )
                    return True

            return False

        except Exception as e:
            logger.warning(
                f"Error checking user response for conversation {conversation.id}: {e}"
            )
            return False

    async def filter_unresponded_messages(
        self,
        user_id: str,
        user_slack_id: str,
        messages: list[TriageClassification],
    ) -> list[TriageClassification]:
        """
        Filter out individual messages the user has already responded to.

        This is a simpler version for when conversation grouping isn't needed.

        Args:
            user_id: Alfred user ID
            user_slack_id: User's Slack ID
            messages: List of TriageClassification items

        Returns:
            List of TriageClassification items the user has NOT responded to
        """
        unresponded = []

        by_channel: dict[str, list[TriageClassification]] = {}
        for msg in messages:
            if msg.channel_id not in by_channel:
                by_channel[msg.channel_id] = []
            by_channel[msg.channel_id].append(msg)

        for channel_id, channel_messages in by_channel.items():
            latest_ts = max(m.message_ts for m in channel_messages)

            user_messages_after = await self._get_user_messages_after(
                user_id, user_slack_id, channel_id, latest_ts
            )

            for msg in channel_messages:
                if any(ts > msg.message_ts for ts in user_messages_after):
                    continue

                unresponded.append(msg)

        return unresponded

    async def _get_user_messages_after(
        self, user_id: str, user_slack_id: str, channel_id: str, after_ts: str
    ) -> list[str]:
        """
        Get timestamps of user's messages in a channel after a given timestamp.

        Args:
            user_id: Alfred user ID (for token lookup)
            user_slack_id: User's Slack ID
            channel_id: Channel ID to check
            after_ts: Timestamp to search after

        Returns:
            List of message timestamps from the user
        """
        client = await self._get_user_client(user_id)
        if not client:
            logger.warning(f"No user client for {user_id}, cannot fetch messages")
            return []

        try:
            response = await client.conversations_history(
                channel=channel_id,
                limit=20,
            )

            messages = response.get("messages", [])
            user_message_ts = []

            for msg in messages:
                msg_ts = msg.get("ts", "0")
                msg_user = msg.get("user")

                if msg.get("bot_id") or msg.get("subtype") == "bot_message":
                    continue

                if msg_user == user_slack_id and msg_ts > after_ts:
                    user_message_ts.append(msg_ts)

            return user_message_ts

        except Exception as e:
            logger.warning(f"Error fetching user messages in {channel_id}: {e}")
            return []
