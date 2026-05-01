"""Digest grouping — conversation-aware message grouping for digests."""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Any

from app.db.models.triage import TriageClassification

if TYPE_CHECKING:
    from slack_sdk.web.async_client import AsyncWebClient

logger = logging.getLogger(__name__)

MAX_THREAD_REPLIES = 200


def is_thread_reply(msg: TriageClassification) -> bool:
    """Check if a message is a reply in a thread (not the parent)."""
    return msg.thread_ts is not None and msg.thread_ts != msg.message_ts


@dataclass
class ThreadContext:
    """Context for thread summarization with CONTEXT/NEW distinction."""

    thread_ts: str
    channel_id: str
    context_messages: list[dict[str, Any]]
    new_messages: list[TriageClassification]
    is_first_run: bool

    @property
    def all_user_ids(self) -> set[str]:
        """Get all unique user IDs from context and new messages."""
        user_ids: set[str] = set()
        for msg in self.context_messages:
            if msg.get("user"):
                user_ids.add(msg["user"])
        for msg in self.new_messages:
            if msg.sender_slack_id:
                user_ids.add(msg.sender_slack_id)
        return user_ids


@dataclass
class ConversationGroup:
    """A group of related messages forming a conversation."""

    id: str
    messages: list[TriageClassification]
    conversation_type: str
    channel_id: str
    channel_name: str | None = None
    thread_ts: str | None = None
    topic: str | None = None
    participants: list[str] = field(default_factory=list)
    thread_context: ThreadContext | None = None
    summarization_mode: str = "full"

    @property
    def last_message_ts(self) -> str:
        """Get the timestamp of the most recent message in the conversation."""
        if not self.messages:
            return ""
        return max(m.message_ts for m in self.messages)

    @property
    def first_message_ts(self) -> str:
        """Get the timestamp of the oldest message in the conversation."""
        if not self.messages:
            return ""
        return min(m.message_ts for m in self.messages)

    @property
    def senders(self) -> set[str]:
        """Get unique sender IDs in this conversation."""
        return {m.sender_slack_id for m in self.messages}

    @property
    def sender_names(self) -> list[str]:
        """Get unique sender names in this conversation, ordered by first appearance."""
        seen = set()
        names = []
        for m in self.messages:
            if m.sender_slack_id not in seen:
                seen.add(m.sender_slack_id)
                name = m.sender_name or m.sender_slack_id
                if name not in names:
                    names.append(name)
        return names

    @property
    def priority(self) -> str:
        """Get the highest priority level among messages in this group."""
        priority_order = {"p0": 0, "p1": 1, "p2": 2, "p3": 3}
        highest = 3
        for m in self.messages:
            msg_priority = priority_order.get(m.priority_level, 3)
            if msg_priority < highest:
                highest = msg_priority
        return ["p0", "p1", "p2", "p3"][highest]


class DigestGrouper:
    """Groups triage classifications into conversations for digest summaries."""

    def __init__(self) -> None:
        self._user_clients: dict[str, AsyncWebClient] = {}

    async def _get_user_client(self, user_id: str, db) -> "AsyncWebClient | None":
        """Get a Slack client using the user's OAuth token."""
        if user_id in self._user_clients:
            return self._user_clients[user_id]

        from app.services.slack_user import SlackUserService

        user_svc = SlackUserService(db)
        token = await user_svc.get_raw_token(user_id)
        if not token:
            logger.warning(f"No Slack OAuth token for user {user_id}")
            return None

        from slack_sdk.web.async_client import AsyncWebClient

        client = AsyncWebClient(token=token)
        self._user_clients[user_id] = client
        return client

    async def fetch_thread_context(
        self,
        client: "AsyncWebClient",
        channel_id: str,
        thread_ts: str,
        new_message_ids: set[str],
    ) -> ThreadContext | None:
        """Fetch full thread context for summarization.

        Args:
            client: Slack client with user OAuth token
            channel_id: Channel ID
            thread_ts: Thread timestamp
            new_message_ids: Set of message_ts values for NEW messages

        Returns:
            ThreadContext with CONTEXT/NEW distinction, or None on error
        """
        try:
            response = await client.conversations_replies(
                channel=channel_id,
                ts=thread_ts,
                limit=MAX_THREAD_REPLIES + 50,
            )
            messages = response.get("messages", [])

            if len(messages) > MAX_THREAD_REPLIES:
                dropped = len(messages) - MAX_THREAD_REPLIES
                messages = messages[-MAX_THREAD_REPLIES:]
                logger.info(
                    f"Truncated thread {thread_ts} to {MAX_THREAD_REPLIES} messages, "
                    f"dropped {dropped} oldest"
                )

            new_ts_set = new_message_ids
            context_messages = []

            for msg in messages:
                msg_ts = msg.get("ts", "")
                if msg_ts in new_ts_set:
                    pass
                else:
                    user_id = msg.get("user", "UNKNOWN")
                    text = msg.get("text", "")
                    ts = msg.get("ts", "")
                    context_messages.append(
                        {
                            "user": user_id,
                            "text": text,
                            "ts": ts,
                        }
                    )

            is_first_run = len(context_messages) == 0

            return ThreadContext(
                thread_ts=thread_ts,
                channel_id=channel_id,
                context_messages=context_messages,
                new_messages=[],
                is_first_run=is_first_run,
            )

        except Exception as e:
            logger.warning(f"Failed to fetch thread context for {thread_ts}: {e}")
            return None

    async def group_messages_with_context(
        self,
        messages: list[TriageClassification],
        user_id: str,
        db,
    ) -> list[ConversationGroup]:
        """Group messages with full thread context for better summarization.

        Respects channel-level summary_behavior settings:
        - default: Include all messages and replies
        - initial_only: Only include thread parents, exclude replies

        Args:
            messages: List of TriageClassification items to group
            user_id: User ID for OAuth token lookup
            db: Database session

        Returns:
            List of ConversationGroup objects with thread context enriched
        """
        if not messages:
            return []

        from app.db.repositories.triage import MonitoredChannelRepository

        channel_repo = MonitoredChannelRepository(db)
        channels = await channel_repo.get_by_user(user_id, active_only=False)
        channel_settings = {c.slack_channel_id: c for c in channels}

        filtered_messages = []
        for msg in messages:
            channel = channel_settings.get(msg.channel_id)
            if channel and channel.summary_behavior == "initial_only":
                if is_thread_reply(msg):
                    continue
            filtered_messages.append(msg)

        if len(filtered_messages) != len(messages):
            logger.info(
                f"Filtered {len(messages) - len(filtered_messages)} thread replies "
                f"from channels with initial_only summary_behavior"
            )

        conversations = self.group_messages(filtered_messages)

        client = await self._get_user_client(user_id, db)
        if not client:
            logger.warning("No user client available, skipping thread context fetch")
            return conversations

        channel_groups_to_cluster: list[ConversationGroup] = []

        for conv in conversations:
            if conv.conversation_type == "thread" and conv.thread_ts:
                new_message_ids = {m.message_ts for m in conv.messages}
                thread_ctx = await self.fetch_thread_context(
                    client, conv.channel_id, conv.thread_ts, new_message_ids
                )
                if thread_ctx:
                    thread_ctx.new_messages = conv.messages
                    conv.thread_context = thread_ctx
                    conv.summarization_mode = (
                        "full" if thread_ctx.is_first_run else "thread_incremental"
                    )
            elif conv.conversation_type == "channel" and len(conv.messages) > 1:
                channel_groups_to_cluster.append(conv)

        if channel_groups_to_cluster:
            clustered = await self._cluster_channel_messages(
                channel_groups_to_cluster, user_id, db
            )
            conversations = [
                c
                for c in conversations
                if c.conversation_type != "channel"
                or len(c.messages) == 1
                or c not in channel_groups_to_cluster
            ]
            conversations.extend(clustered)

        return conversations

    async def _cluster_channel_messages(
        self,
        channel_groups: list[ConversationGroup],
        user_id: str,
        db,
    ) -> list[ConversationGroup]:
        """Cluster unthreaded channel messages using LLM.

        Args:
            channel_groups: List of channel conversation groups to cluster
            user_id: User ID for name resolution
            db: Database session

        Returns:
            List of ConversationGroup objects with LLM-identified boundaries
        """
        from app.core.redis import get_redis
        from app.services.message_clustering import (
            cluster_messages_with_llm,
            partition_messages,
        )
        from app.services.triage_enrichment import resolve_user_names_batch

        all_channel_messages: list[TriageClassification] = []
        for group in channel_groups:
            all_channel_messages.extend(group.messages)

        if len(all_channel_messages) == 1:
            return channel_groups

        batches = partition_messages(all_channel_messages)

        redis_client = await get_redis()
        all_user_ids = {m.sender_slack_id for m in all_channel_messages}
        from app.services.slack import SlackService

        slack_service = SlackService()
        user_names = await resolve_user_names_batch(
            slack_service, redis_client, all_user_ids
        )

        all_clusters = []
        for batch in batches:
            clusters = await cluster_messages_with_llm(batch, user_names)
            all_clusters.extend(clusters)

        conversations = []
        for i, cluster in enumerate(all_clusters):
            if not cluster.messages:
                continue
            sorted_msgs = sorted(cluster.messages, key=lambda m: m.message_ts)
            conversations.append(
                ConversationGroup(
                    id=f"channel:{sorted_msgs[0].channel_id}:cluster{i}",
                    messages=sorted_msgs,
                    conversation_type="channel",
                    channel_id=sorted_msgs[0].channel_id,
                    channel_name=sorted_msgs[0].channel_name,
                    participants=list({m.sender_slack_id for m in sorted_msgs}),
                    summarization_mode="full",
                )
            )

        logger.info(
            f"LLM clustering: {len(all_channel_messages)} channel messages -> "
            f"{len(conversations)} conversations"
        )
        return conversations

    def group_messages(
        self, messages: list[TriageClassification]
    ) -> list[ConversationGroup]:
        """
        Group messages into conversations.

        Strategy:
        1. Thread messages (same thread_ts) → one conversation (deterministic)
           - Includes both the parent message AND all replies
        2. DM messages (same channel) → one conversation per DM channel
        3. Channel messages without thread → grouped by LLM later

        Args:
            messages: List of TriageClassification items to group

        Returns:
            List of ConversationGroup objects
        """
        if not messages:
            return []

        conversations: list[ConversationGroup] = []
        thread_groups: dict[str, list[TriageClassification]] = {}
        dm_groups: dict[str, list[TriageClassification]] = {}
        channel_messages: list[TriageClassification] = []

        all_thread_ts_values: set[str] = set()
        for msg in messages:
            if msg.thread_ts:
                all_thread_ts_values.add(msg.thread_ts)

        for msg in messages:
            if msg.thread_ts:
                if msg.thread_ts not in thread_groups:
                    thread_groups[msg.thread_ts] = []
                thread_groups[msg.thread_ts].append(msg)
            elif msg.message_ts in all_thread_ts_values:
                if msg.message_ts not in thread_groups:
                    thread_groups[msg.message_ts] = []
                thread_groups[msg.message_ts].append(msg)
            elif msg.channel_id.startswith("D"):
                if msg.channel_id not in dm_groups:
                    dm_groups[msg.channel_id] = []
                dm_groups[msg.channel_id].append(msg)
            else:
                channel_messages.append(msg)

        # Create thread conversations
        for thread_ts, msgs in thread_groups.items():
            sorted_msgs = sorted(msgs, key=lambda m: m.message_ts)
            conversations.append(
                ConversationGroup(
                    id=f"thread:{thread_ts}",
                    messages=sorted_msgs,
                    conversation_type="thread",
                    channel_id=sorted_msgs[0].channel_id,
                    channel_name=sorted_msgs[0].channel_name,
                    thread_ts=thread_ts,
                    participants=list({m.sender_slack_id for m in sorted_msgs}),
                )
            )

        # Create DM conversations
        for channel_id, msgs in dm_groups.items():
            sorted_msgs = sorted(msgs, key=lambda m: m.message_ts)
            conversations.append(
                ConversationGroup(
                    id=f"dm:{channel_id}",
                    messages=sorted_msgs,
                    conversation_type="dm",
                    channel_id=channel_id,
                    channel_name=sorted_msgs[0].channel_name,
                    participants=list({m.sender_slack_id for m in sorted_msgs}),
                )
            )

        # Group channel messages by channel first (LLM will subdivide)
        channel_by_id: dict[str, list[TriageClassification]] = {}
        for msg in channel_messages:
            if msg.channel_id not in channel_by_id:
                channel_by_id[msg.channel_id] = []
            channel_by_id[msg.channel_id].append(msg)

        # Create channel conversation groups (one per channel for now)
        # The LLM-based subdivision will happen in the summarization step
        for channel_id, msgs in channel_by_id.items():
            sorted_msgs = sorted(msgs, key=lambda m: m.message_ts)
            conversations.append(
                ConversationGroup(
                    id=f"channel:{channel_id}",
                    messages=sorted_msgs,
                    conversation_type="channel",
                    channel_id=channel_id,
                    channel_name=sorted_msgs[0].channel_name,
                    participants=list({m.sender_slack_id for m in sorted_msgs}),
                )
            )

        logger.info(
            f"Grouped {len(messages)} messages into {len(conversations)} conversations "
            f"({len(thread_groups)} threads, {len(dm_groups)} DMs, {len(channel_by_id)} channels)"
        )

        return conversations

    async def persist_conversations(
        self,
        conversations: list[ConversationGroup],
        user_id: str,
        db,
    ) -> list:
        """Persist ConversationGroups as ConversationSummary records.

        This creates ConversationSummary records for each conversation,
        links child messages via conversation_summary_id, and returns
        the persisted records.

        Args:
            conversations: List of ConversationGroup objects to persist
            user_id: User ID for the summaries
            db: Database session

        Returns:
            List of persisted ConversationSummary records
        """
        from app.db.models.conversation_summary import ConversationSummary
        from app.db.repositories.conversation_summary import ConversationSummaryRepository
        from sqlalchemy import update

        repo = ConversationSummaryRepository(db)
        persisted = []

        for conv in conversations:
            if not conv.messages:
                continue

            sorted_msgs = sorted(conv.messages, key=lambda m: m.message_ts)
            first_msg = sorted_msgs[0]
            last_msg = sorted_msgs[-1]

            participants_data = []
            seen_ids = set()
            for m in sorted_msgs:
                if m.sender_slack_id not in seen_ids:
                    seen_ids.add(m.sender_slack_id)
                    participants_data.append({
                        "slack_id": m.sender_slack_id,
                        "name": m.sender_name,
                    })

            summary = ConversationSummary(
                user_id=user_id,
                conversation_type=conv.conversation_type,
                channel_id=conv.channel_id,
                channel_name=conv.channel_name,
                thread_ts=conv.thread_ts,
                abstract=conv.topic or f"{len(sorted_msgs)} messages",
                participants=participants_data,
                message_count=len(sorted_msgs),
                priority_level=conv.priority,
                first_message_ts=first_msg.message_ts,
                slack_permalink=first_msg.slack_permalink,
                first_message_at=first_msg.created_at,
                last_message_at=last_msg.created_at,
            )

            summary = await repo.create(summary)

            await db.execute(
                update(TriageClassification)
                .where(TriageClassification.id.in_([m.id for m in sorted_msgs]))
                .values(conversation_summary_id=summary.id)
            )
            await db.flush()

            for msg in sorted_msgs:
                msg.conversation_summary_id = summary.id

            persisted.append(summary)

        logger.info(
            f"Persisted {len(persisted)} conversation summaries for user {user_id}"
        )

        return persisted

    async def group_channel_messages_with_llm(
        self,
        messages: list[TriageClassification],
        channel_history: list[dict[str, Any]],
    ) -> list[ConversationGroup]:
        """
        Use LLM to identify distinct conversations within channel messages.

        This is called when there are multiple messages in a channel without threads,
        and we need to determine if they're part of the same conversation or separate.

        Args:
            messages: List of TriageClassification items in the same channel
            channel_history: Recent channel history for context

        Returns:
            List of ConversationGroup objects with LLM-identified boundaries
        """
        if not messages:
            return []

        if len(messages) == 1:
            # Single message - no need for LLM
            return [
                ConversationGroup(
                    id=f"channel:{messages[0].channel_id}:{messages[0].message_ts}",
                    messages=[messages[0]],
                    conversation_type="channel",
                    channel_id=messages[0].channel_id,
                    channel_name=messages[0].channel_name,
                    participants=[messages[0].sender_slack_id],
                )
            ]

        # Use LLM to identify conversation boundaries
        from app.core.config import get_settings
        from app.core.llm import LLMMessage, get_llm_provider

        settings = get_settings()
        provider = get_llm_provider(
            settings.web_search_synthesis_model or "gemini-2.5-flash-lite"
        )

        # Build message context for LLM
        message_list = []
        for i, msg in enumerate(messages):
            sender = msg.sender_name or f"<@{msg.sender_slack_id}>"
            time_str = msg.created_at.strftime("%H:%M") if msg.created_at else ""
            abstract = msg.abstract or "Message"
            message_list.append(f"{i + 1}. [{time_str}] {sender}: {abstract[:100]}")

        system_prompt = f"""You are analyzing Slack messages to identify distinct conversations.

Messages from the same channel:
{chr(10).join(message_list)}

Task: Group these messages into distinct conversations. Messages are in the same conversation if:
- They're on the same topic
- Users are responding to each other
- They reference or build on each other

Output JSON format:
{{
  "conversations": [
    {{
      "message_indices": [1, 2, 3],
      "topic": "Brief topic description"
    }}
  ]
}}

Message indices are 1-based (matching the numbered list above).
Each message should appear in exactly one conversation.
If messages seem unrelated, put each in its own conversation.

Output ONLY the JSON, no other text."""

        try:
            response = await provider.generate(
                messages=[LLMMessage(role="user", content=system_prompt)],
                temperature=0.1,
                max_tokens=500,
            )

            # Parse LLM response
            import json

            response_text = response.strip()
            # Remove markdown code blocks if present
            if response_text.startswith("```"):
                response_text = response_text.split("\n", 1)[1]
            if response_text.endswith("```"):
                response_text = response_text.rsplit("```", 1)[0]

            result = json.loads(response_text)
            conversations_data = result.get("conversations", [])

            # Build ConversationGroups from LLM output
            conversations = []
            for i, conv_data in enumerate(conversations_data):
                indices = conv_data.get("message_indices", [])
                # Convert 1-based to 0-based indices
                conv_messages = [
                    messages[idx - 1] for idx in indices if 0 < idx <= len(messages)
                ]

                if conv_messages:
                    sorted_msgs = sorted(conv_messages, key=lambda m: m.message_ts)
                    conversations.append(
                        ConversationGroup(
                            id=f"channel:{sorted_msgs[0].channel_id}:conv{i}",
                            messages=sorted_msgs,
                            conversation_type="channel",
                            channel_id=sorted_msgs[0].channel_id,
                            channel_name=sorted_msgs[0].channel_name,
                            topic=conv_data.get("topic"),
                            participants=list({m.sender_slack_id for m in sorted_msgs}),
                        )
                    )

            logger.info(
                f"LLM grouped {len(messages)} channel messages into {len(conversations)} conversations"
            )
            return conversations

        except Exception as e:
            logger.warning(f"LLM conversation grouping failed, using single group: {e}")
            # Fallback: single conversation
            sorted_msgs = sorted(messages, key=lambda m: m.message_ts)
            return [
                ConversationGroup(
                    id=f"channel:{sorted_msgs[0].channel_id}",
                    messages=sorted_msgs,
                    conversation_type="channel",
                    channel_id=sorted_msgs[0].channel_id,
                    channel_name=sorted_msgs[0].channel_name,
                    participants=list({m.sender_slack_id for m in sorted_msgs}),
                )
            ]
