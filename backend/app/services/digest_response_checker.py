"""Digest response checker — detect if user has responded to messages."""

import logging
from datetime import datetime

from app.db.models.triage import TriageClassification
from app.services.digest_grouper import ConversationGroup
from app.services.slack import SlackService

logger = logging.getLogger(__name__)


class DigestResponseChecker:
    """Checks if the user has responded to messages or conversations."""

    def __init__(self) -> None:
        self.slack_service = SlackService()

    async def filter_unresponded_conversations(
        self,
        user_id: str,
        user_slack_id: str,
        conversations: list[ConversationGroup],
    ) -> list[ConversationGroup]:
        """
        Filter out conversations the user has already responded to.

        A user has responded to a conversation if:
        1. They reacted to any message in the conversation, OR
        2. They posted a message after the last message in the conversation

        Args:
            user_id: Alfred user ID
            user_slack_id: User's Slack ID
            conversations: List of ConversationGroup objects

        Returns:
            List of ConversationGroup objects the user has NOT responded to
        """
        unresponded = []

        for conv in conversations:
            # Check if user reacted (stored in DB from reaction_added event)
            if conv.has_user_reacted():
                logger.info(f"Skipping conversation {conv.id}: user reacted")
                continue

            # Check if user already marked as responded (user_responded_at set)
            if conv.has_user_responded():
                logger.info(f"Skipping conversation {conv.id}: user responded")
                continue

            # Check if user responded via message (fetch from Slack)
            user_responded = await self._check_user_message_response(
                user_slack_id, conv
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
        self, user_slack_id: str, conversation: ConversationGroup
    ) -> bool:
        """
        Check if user posted a message after the last message in the conversation.

        Args:
            user_slack_id: User's Slack ID
            conversation: ConversationGroup to check

        Returns:
            True if user posted after the conversation, False otherwise
        """
        try:
            # Fetch recent messages from the channel/DM
            if conversation.conversation_type == "thread":
                # For threads, check if user posted in the thread
                response = await self.slack_service.client.conversations_replies(
                    channel=conversation.channel_id,
                    ts=conversation.thread_ts,
                    limit=50,
                )
            else:
                # For channels/DMs, fetch recent history
                response = await self.slack_service.client.conversations_history(
                    channel=conversation.channel_id,
                    limit=20,
                )

            messages = response.get("messages", [])
            last_conv_ts = conversation.last_message_ts

            # Check if any message from the user is after the last conversation message
            for msg in messages:
                msg_ts = msg.get("ts", "0")
                msg_user = msg.get("user")

                # Skip bot messages
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
            # On error, assume not responded (conservative)
            return False

    async def mark_responded_messages(
        self,
        user_id: str,
        conversations: list[ConversationGroup],
    ) -> int:
        """
        Mark messages in responded conversations as responded.

        This should be called after filtering to update the database
        with the user's response status.

        Args:
            user_id: Alfred user ID
            conversations: List of ConversationGroup objects that were responded to

        Returns:
            Total count of messages marked as responded
        """
        from app.db.session import async_session_maker

        total_marked = 0

        async with async_session_maker() as db:
            for conv in conversations:
                # Mark all messages in the conversation as responded
                for msg in conv.messages:
                    if msg.user_responded_at is None:
                        # Use current time as response time
                        msg.user_responded_at = datetime.utcnow()
                        await db.flush()
                        total_marked += 1

            await db.commit()

        return total_marked

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

        # Group by channel for efficient API calls
        by_channel: dict[str, list[TriageClassification]] = {}
        for msg in messages:
            if msg.channel_id not in by_channel:
                by_channel[msg.channel_id] = []
            by_channel[msg.channel_id].append(msg)

        for channel_id, channel_messages in by_channel.items():
            # Get the latest message timestamp in this channel
            latest_ts = max(m.message_ts for m in channel_messages)

            # Check if user already reacted (stored in DB)
            reacted_ts_set = {
                m.message_ts for m in channel_messages if m.user_reacted_at is not None
            }

            # Fetch recent history to check for user messages
            user_messages_after = await self._get_user_messages_after(
                user_slack_id, channel_id, latest_ts
            )

            for msg in channel_messages:
                # Skip if user reacted
                if msg.message_ts in reacted_ts_set:
                    continue

                # Skip if user posted after this message
                if any(ts > msg.message_ts for ts in user_messages_after):
                    continue

                unresponded.append(msg)

        return unresponded

    async def _get_user_messages_after(
        self, user_slack_id: str, channel_id: str, after_ts: str
    ) -> list[str]:
        """
        Get timestamps of user's messages in a channel after a given timestamp.

        Args:
            user_slack_id: User's Slack ID
            channel_id: Channel ID to check
            after_ts: Timestamp to search after

        Returns:
            List of message timestamps from the user
        """
        try:
            response = await self.slack_service.client.conversations_history(
                channel=channel_id,
                limit=20,
            )

            messages = response.get("messages", [])
            user_message_ts = []

            for msg in messages:
                msg_ts = msg.get("ts", "0")
                msg_user = msg.get("user")

                # Skip bot messages
                if msg.get("bot_id") or msg.get("subtype") == "bot_message":
                    continue

                if msg_user == user_slack_id and msg_ts > after_ts:
                    user_message_ts.append(msg_ts)

            return user_message_ts

        except Exception as e:
            logger.warning(f"Error fetching user messages in {channel_id}: {e}")
            return []
