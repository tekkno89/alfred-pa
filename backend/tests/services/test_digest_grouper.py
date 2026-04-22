"""Tests for digest_grouper service."""

import pytest
from datetime import datetime
from unittest.mock import AsyncMock, patch
import uuid

from app.services.digest_grouper import DigestGrouper, ConversationGroup
from app.db.models.triage import TriageClassification


def create_classification(
    channel_id: str,
    thread_ts: str | None,
    sender_id: str,
    message_ts: str,
    channel_name: str | None = None,
    sender_name: str | None = None,
) -> TriageClassification:
    """Helper to create a TriageClassification for testing."""
    return TriageClassification(
        id=str(uuid.uuid4()),
        user_id="test-user",
        sender_slack_id=sender_id,
        sender_name=sender_name or f"User-{sender_id}",
        channel_id=channel_id,
        channel_name=channel_name or f"channel-{channel_id}",
        message_ts=message_ts,
        thread_ts=thread_ts,
        priority_level="p1",
        confidence=0.9,
        classification_path="channel",
        created_at=datetime.utcnow(),
    )


class TestDigestGrouper:
    """Tests for DigestGrouper."""

    def test_group_empty_messages(self):
        """Empty input returns empty list."""
        grouper = DigestGrouper()
        result = grouper.group_messages([])
        assert result == []

    def test_group_single_message(self):
        """Single message becomes single conversation."""
        grouper = DigestGrouper()
        msg = create_classification("C123", None, "U1", "100.1")
        result = grouper.group_messages([msg])

        assert len(result) == 1
        assert result[0].conversation_type == "channel"
        assert len(result[0].messages) == 1

    def test_group_thread_messages(self):
        """Messages with same thread_ts are grouped together."""
        grouper = DigestGrouper()
        messages = [
            create_classification("C123", "T1", "U1", "100.1"),
            create_classification("C123", "T1", "U2", "100.2"),
            create_classification("C123", "T1", "U3", "100.3"),
        ]
        result = grouper.group_messages(messages)

        assert len(result) == 1
        assert result[0].conversation_type == "thread"
        assert result[0].thread_ts == "T1"
        assert len(result[0].messages) == 3
        assert result[0].senders == {"U1", "U2", "U3"}

    def test_group_multiple_threads(self):
        """Different threads create separate conversations."""
        grouper = DigestGrouper()
        messages = [
            create_classification("C123", "T1", "U1", "100.1"),
            create_classification("C123", "T1", "U2", "100.2"),
            create_classification("C123", "T2", "U1", "101.1"),
            create_classification("C123", "T2", "U3", "101.2"),
        ]
        result = grouper.group_messages(messages)

        assert len(result) == 2
        thread_convs = {c.thread_ts: c for c in result}
        assert "T1" in thread_convs
        assert "T2" in thread_convs
        assert len(thread_convs["T1"].messages) == 2
        assert len(thread_convs["T2"].messages) == 2

    def test_group_dm_messages(self):
        """DM messages are grouped by channel."""
        grouper = DigestGrouper()
        messages = [
            create_classification("D123", None, "U1", "100.1"),
            create_classification("D123", None, "U2", "100.2"),
            create_classification("D456", None, "U1", "200.1"),
        ]
        result = grouper.group_messages(messages)

        assert len(result) == 2
        dm_convs = {c.channel_id: c for c in result}
        assert "D123" in dm_convs
        assert "D456" in dm_convs
        assert dm_convs["D123"].conversation_type == "dm"
        assert len(dm_convs["D123"].messages) == 2
        assert len(dm_convs["D456"].messages) == 1

    def test_group_channel_messages_without_thread(self):
        """Channel messages without thread_ts are grouped by channel."""
        grouper = DigestGrouper()
        messages = [
            create_classification("C123", None, "U1", "100.1"),
            create_classification("C123", None, "U2", "100.2"),
            create_classification("C456", None, "U3", "200.1"),
        ]
        result = grouper.group_messages(messages)

        assert len(result) == 2
        channel_convs = {c.channel_id: c for c in result}
        assert "C123" in channel_convs
        assert "C456" in channel_convs
        assert channel_convs["C123"].conversation_type == "channel"
        assert len(channel_convs["C123"].messages) == 2

    def test_group_mixed_messages(self):
        """Mix of threads, DMs, and channel messages."""
        grouper = DigestGrouper()
        messages = [
            # Thread 1
            create_classification("C123", "T1", "U1", "100.1"),
            create_classification("C123", "T1", "U2", "100.2"),
            # Thread 2
            create_classification("C123", "T2", "U1", "101.1"),
            # Non-thread channel
            create_classification("C456", None, "U3", "200.1"),
            create_classification("C456", None, "U4", "200.2"),
            # DM
            create_classification("D123", None, "U5", "300.1"),
        ]
        result = grouper.group_messages(messages)

        assert len(result) == 4

        # Check types
        types = [c.conversation_type for c in result]
        assert types.count("thread") == 2
        assert types.count("channel") == 1
        assert types.count("dm") == 1

    def test_messages_sorted_by_ts(self):
        """Messages within conversation are sorted by message_ts."""
        grouper = DigestGrouper()
        messages = [
            create_classification("C123", "T1", "U1", "100.5"),
            create_classification("C123", "T1", "U2", "100.1"),
            create_classification("C123", "T1", "U3", "100.3"),
        ]
        result = grouper.group_messages(messages)

        assert len(result) == 1
        msg_tses = [m.message_ts for m in result[0].messages]
        assert msg_tses == ["100.1", "100.3", "100.5"]


class TestConversationGroup:
    """Tests for ConversationGroup dataclass."""

    def test_last_message_ts(self):
        """Returns highest message_ts."""
        messages = [
            create_classification("C123", "T1", "U1", "100.1"),
            create_classification("C123", "T1", "U2", "100.5"),
            create_classification("C123", "T1", "U3", "100.3"),
        ]
        conv = ConversationGroup(
            id="test",
            messages=messages,
            conversation_type="thread",
            channel_id="C123",
            participants=["U1", "U2", "U3"],
        )
        assert conv.last_message_ts == "100.5"

    def test_first_message_ts(self):
        """Returns lowest message_ts."""
        messages = [
            create_classification("C123", "T1", "U1", "100.5"),
            create_classification("C123", "T1", "U2", "100.1"),
            create_classification("C123", "T1", "U3", "100.3"),
        ]
        conv = ConversationGroup(
            id="test",
            messages=messages,
            conversation_type="thread",
            channel_id="C123",
            participants=["U1", "U2", "U3"],
        )
        assert conv.first_message_ts == "100.1"

    def test_senders_property(self):
        """Returns unique sender IDs."""
        messages = [
            create_classification("C123", "T1", "U1", "100.1"),
            create_classification("C123", "T1", "U2", "100.2"),
            create_classification("C123", "T1", "U1", "100.3"),  # Duplicate sender
        ]
        conv = ConversationGroup(
            id="test",
            messages=messages,
            conversation_type="thread",
            channel_id="C123",
            participants=["U1", "U2"],
        )
        assert conv.senders == {"U1", "U2"}

    def test_sender_names_property(self):
        """Returns unique sender names in order of first appearance."""
        messages = [
            create_classification("C123", "T1", "U1", "100.1", sender_name="Alice"),
            create_classification("C123", "T1", "U2", "100.2", sender_name="Bob"),
            create_classification(
                "C123", "T1", "U1", "100.3", sender_name="Alice"
            ),  # Duplicate
        ]
        conv = ConversationGroup(
            id="test",
            messages=messages,
            conversation_type="thread",
            channel_id="C123",
            participants=["U1", "U2"],
        )
        assert conv.sender_names == ["Alice", "Bob"]

    def test_sender_names_falls_back_to_id(self):
        """Falls back to sender_slack_id when sender_name is None."""
        msg = create_classification("C123", "T1", "U1", "100.1", sender_name=None)
        # Clear the default name to test fallback
        msg.sender_name = None
        conv = ConversationGroup(
            id="test",
            messages=[msg],
            conversation_type="thread",
            channel_id="C123",
            participants=["U1"],
        )
        assert conv.sender_names == ["U1"]

    def test_has_user_reacted_true(self):
        """Returns True if any message has user_reacted_at."""
        msg1 = create_classification("C123", "T1", "U1", "100.1")
        msg2 = create_classification("C123", "T1", "U2", "100.2")
        msg2.user_reacted_at = datetime.utcnow()

        conv = ConversationGroup(
            id="test",
            messages=[msg1, msg2],
            conversation_type="thread",
            channel_id="C123",
            participants=["U1", "U2"],
        )
        assert conv.has_user_reacted() is True

    def test_has_user_reacted_false(self):
        """Returns False if no message has user_reacted_at."""
        messages = [
            create_classification("C123", "T1", "U1", "100.1"),
            create_classification("C123", "T1", "U2", "100.2"),
        ]
        conv = ConversationGroup(
            id="test",
            messages=messages,
            conversation_type="thread",
            channel_id="C123",
            participants=["U1", "U2"],
        )
        assert conv.has_user_reacted() is False

    def test_has_user_responded_true(self):
        """Returns True if any message has user_responded_at."""
        msg1 = create_classification("C123", "T1", "U1", "100.1")
        msg2 = create_classification("C123", "T1", "U2", "100.2")
        msg2.user_responded_at = datetime.utcnow()

        conv = ConversationGroup(
            id="test",
            messages=[msg1, msg2],
            conversation_type="thread",
            channel_id="C123",
            participants=["U1", "U2"],
        )
        assert conv.has_user_responded() is True

    def test_empty_messages_edge_case(self):
        """Handles empty messages list gracefully."""
        conv = ConversationGroup(
            id="test",
            messages=[],
            conversation_type="thread",
            channel_id="C123",
            participants=[],
        )
        assert conv.last_message_ts == ""
        assert conv.first_message_ts == ""
        assert conv.senders == set()


class TestDigestGrouperLLM:
    """Tests for LLM-based channel grouping."""

    @pytest.mark.asyncio
    async def test_group_single_message_no_llm(self):
        """Single message doesn't require LLM."""
        grouper = DigestGrouper()
        messages = [create_classification("C123", None, "U1", "100.1")]

        result = await grouper.group_channel_messages_with_llm(messages, [])

        assert len(result) == 1
        assert result[0].conversation_type == "channel"

    @pytest.mark.asyncio
    async def test_group_with_llm_success(self):
        """LLM successfully groups messages."""
        grouper = DigestGrouper()
        messages = [
            create_classification("C123", None, "U1", "100.1", sender_name="Alice"),
            create_classification("C123", None, "U2", "100.2", sender_name="Bob"),
        ]

        mock_response = """
        {
            "conversations": [
                {"message_indices": [1, 2], "topic": "Project discussion"}
            ]
        }
        """

        with patch("app.core.llm.get_llm_provider") as mock_get_provider:
            mock_llm = AsyncMock()
            mock_llm.generate = AsyncMock(return_value=mock_response)
            mock_get_provider.return_value = mock_llm

            result = await grouper.group_channel_messages_with_llm(messages, [])

            assert len(result) == 1
            assert result[0].topic == "Project discussion"
            assert len(result[0].messages) == 2

    @pytest.mark.asyncio
    async def test_group_llm_separate_conversations(self):
        """LLM identifies separate conversations."""
        grouper = DigestGrouper()
        messages = [
            create_classification("C123", None, "U1", "100.1", sender_name="Alice"),
            create_classification("C123", None, "U2", "100.2", sender_name="Bob"),
            create_classification("C123", None, "U3", "100.3", sender_name="Carol"),
        ]

        mock_response = """
        {
            "conversations": [
                {"message_indices": [1, 2], "topic": "Project A"},
                {"message_indices": [3], "topic": "Project B"}
            ]
        }
        """

        with patch("app.core.llm.get_llm_provider") as mock_get_provider:
            mock_llm = AsyncMock()
            mock_llm.generate = AsyncMock(return_value=mock_response)
            mock_get_provider.return_value = mock_llm

            result = await grouper.group_channel_messages_with_llm(messages, [])

            assert len(result) == 2

    @pytest.mark.asyncio
    async def test_group_llm_fallback_on_error(self):
        """Falls back to single group on LLM error."""
        grouper = DigestGrouper()
        messages = [
            create_classification("C123", None, "U1", "100.1"),
            create_classification("C123", None, "U2", "100.2"),
        ]

        with patch("app.core.llm.get_llm_provider") as mock_get_provider:
            mock_llm = AsyncMock()
            mock_llm.generate = AsyncMock(side_effect=Exception("LLM error"))
            mock_get_provider.return_value = mock_llm

            result = await grouper.group_channel_messages_with_llm(messages, [])

            # Falls back to single conversation
            assert len(result) == 1
            assert len(result[0].messages) == 2

    @pytest.mark.asyncio
    async def test_group_llm_separate_conversations(self):
        """LLM identifies separate conversations."""
        grouper = DigestGrouper()
        messages = [
            create_classification("C123", None, "U1", "100.1", sender_name="Alice"),
            create_classification("C123", None, "U2", "100.2", sender_name="Bob"),
            create_classification("C123", None, "U3", "100.3", sender_name="Carol"),
        ]

        mock_response = """
        {
            "conversations": [
                {"message_indices": [1, 2], "topic": "Project A"},
                {"message_indices": [3], "topic": "Project B"}
            ]
        }
        """

        with patch("app.core.llm.get_llm_provider") as mock_get_provider:
            mock_llm = AsyncMock()
            mock_llm.generate = AsyncMock(return_value=mock_response)
            mock_get_provider.return_value = mock_llm

            result = await grouper.group_channel_messages_with_llm(messages, [])

            assert len(result) == 2

    @pytest.mark.asyncio
    async def test_group_llm_fallback_on_error(self):
        """Falls back to single group on LLM error."""
        grouper = DigestGrouper()
        messages = [
            create_classification("C123", None, "U1", "100.1"),
            create_classification("C123", None, "U2", "100.2"),
        ]

        with patch("app.core.llm.get_llm_provider") as mock_get_provider:
            mock_llm = AsyncMock()
            mock_llm.generate = AsyncMock(side_effect=Exception("LLM error"))
            mock_get_provider.return_value = mock_llm

            result = await grouper.group_channel_messages_with_llm(messages, [])

            # Falls back to single conversation
            assert len(result) == 1
            assert len(result[0].messages) == 2
