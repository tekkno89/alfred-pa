"""Digest grouping — conversation-aware message grouping for digests."""

import logging
from dataclasses import dataclass, field
from typing import Any

from app.db.models.triage import TriageClassification

logger = logging.getLogger(__name__)


@dataclass
class ConversationGroup:
    """A group of related messages forming a conversation."""

    id: str
    messages: list[TriageClassification]
    conversation_type: str  # "thread" | "channel" | "dm"
    channel_id: str
    channel_name: str | None = None
    thread_ts: str | None = None
    topic: str | None = None
    participants: list[str] = field(default_factory=list)

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


class DigestGrouper:
    """Groups triage classifications into conversations for digest summaries."""

    def __init__(self) -> None:
        pass

    def group_messages(
        self, messages: list[TriageClassification]
    ) -> list[ConversationGroup]:
        """
        Group messages into conversations.

        Strategy:
        1. Thread messages (same thread_ts) → one conversation (deterministic)
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

        for msg in messages:
            if msg.thread_ts:
                # Thread message - group by thread_ts
                if msg.thread_ts not in thread_groups:
                    thread_groups[msg.thread_ts] = []
                thread_groups[msg.thread_ts].append(msg)
            elif msg.channel_id.startswith("D"):
                # DM - group by channel
                if msg.channel_id not in dm_groups:
                    dm_groups[msg.channel_id] = []
                dm_groups[msg.channel_id].append(msg)
            else:
                # Channel message without thread - will be grouped by LLM
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
