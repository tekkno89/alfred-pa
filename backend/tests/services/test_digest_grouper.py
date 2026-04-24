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


class TestThreadContext:
    """Tests for thread context fetching and CONTEXT/NEW distinction."""

    @pytest.mark.asyncio
    async def test_fetch_thread_context_distinguishes_context_and_new(self):
        """Thread context separates earlier messages from NEW messages."""
        grouper = DigestGrouper()

        mock_client = AsyncMock()
        mock_client.conversations_replies = AsyncMock(
            return_value={
                "messages": [
                    {"ts": "100.1", "user": "U1", "text": "First message"},
                    {"ts": "100.2", "user": "U2", "text": "Second message"},
                    {"ts": "100.3", "user": "U1", "text": "Third message"},
                ]
            }
        )

        new_message_ids = {"100.3"}
        result = await grouper.fetch_thread_context(
            mock_client, "C123", "100.1", new_message_ids
        )

        assert result is not None
        assert len(result.context_messages) == 2
        assert result.is_first_run == False
        assert result.thread_ts == "100.1"
        assert result.channel_id == "C123"

    @pytest.mark.asyncio
    async def test_fetch_thread_context_detects_first_run(self):
        """First-run detection when all messages are NEW."""
        grouper = DigestGrouper()

        mock_client = AsyncMock()
        mock_client.conversations_replies = AsyncMock(
            return_value={
                "messages": [
                    {"ts": "100.1", "user": "U1", "text": "First message"},
                    {"ts": "100.2", "user": "U2", "text": "Second message"},
                ]
            }
        )

        new_message_ids = {"100.1", "100.2"}
        result = await grouper.fetch_thread_context(
            mock_client, "C123", "100.1", new_message_ids
        )

        assert result is not None
        assert result.is_first_run == True
        assert len(result.context_messages) == 0

    @pytest.mark.asyncio
    async def test_fetch_thread_context_truncates_long_threads(self):
        """Thread truncation keeps most recent 200 messages."""
        grouper = DigestGrouper()

        messages = [
            {"ts": f"{i}.0", "user": "U1", "text": f"Message {i}"}
            for i in range(250)
        ]

        mock_client = AsyncMock()
        mock_client.conversations_replies = AsyncMock(
            return_value={"messages": messages}
        )

        new_message_ids = {m["ts"] for m in messages[-5:]}
        result = await grouper.fetch_thread_context(
            mock_client, "C123", "1.0", new_message_ids
        )

        assert result is not None
        assert len(result.context_messages) <= 200

    @pytest.mark.asyncio
    async def test_fetch_thread_context_handles_error(self):
        """Returns None on error."""
        grouper = DigestGrouper()

        mock_client = AsyncMock()
        mock_client.conversations_replies = AsyncMock(
            side_effect=Exception("API error")
        )

        result = await grouper.fetch_thread_context(
            mock_client, "C123", "100.1", {"100.2"}
        )

        assert result is None

    @pytest.mark.asyncio
    async def test_thread_context_all_user_ids(self):
        """all_user_ids property returns unique user IDs from context and new."""
        from app.services.digest_grouper import ThreadContext

        msg1 = create_classification("C123", "100.1", "U1", "100.3")
        msg2 = create_classification("C123", "100.1", "U2", "100.4")

        thread_ctx = ThreadContext(
            thread_ts="100.1",
            channel_id="C123",
            context_messages=[
                {"user": "U3", "text": "Context 1", "ts": "100.1"},
                {"user": "U4", "text": "Context 2", "ts": "100.2"},
            ],
            new_messages=[msg1, msg2],
            is_first_run=False,
        )

        user_ids = thread_ctx.all_user_ids
        assert user_ids == {"U1", "U2", "U3", "U4"}


class TestConversationGroupSummarizationMode:
    """Tests for summarization_mode property."""

    def test_summarization_mode_defaults_to_full(self):
        """Default summarization mode is 'full'."""
        msg = create_classification("C123", None, "U1", "100.1")
        conv = ConversationGroup(
            id="test",
            messages=[msg],
            conversation_type="channel",
            channel_id="C123",
            participants=["U1"],
        )
        assert conv.summarization_mode == "full"

    def test_summarization_mode_can_be_set(self):
        """Summarization mode can be set."""
        msg = create_classification("C123", "T1", "U1", "100.1")
        conv = ConversationGroup(
            id="test",
            messages=[msg],
            conversation_type="thread",
            channel_id="C123",
            thread_ts="T1",
            participants=["U1"],
            summarization_mode="thread_incremental",
        )
        assert conv.summarization_mode == "thread_incremental"


class TestDigestGrouperWithContext:
    """Tests for group_messages_with_context with thread context."""

    @pytest.mark.asyncio
    async def test_group_with_context_enriches_threads(self):
        """Thread messages get context enrichment."""
        grouper = DigestGrouper()
        messages = [
            create_classification("C123", "T1", "U1", "100.1"),
            create_classification("C123", "T1", "U2", "100.2"),
        ]

        mock_client = AsyncMock()
        mock_client.conversations_replies = AsyncMock(
            return_value={
                "messages": [
                    {"ts": "100.0", "user": "U3", "text": "Parent"},
                    {"ts": "100.1", "user": "U1", "text": "Reply 1"},
                    {"ts": "100.2", "user": "U2", "text": "Reply 2"},
                ]
            }
        )

        mock_db = AsyncMock()

        with patch.object(
            grouper, "_get_user_client", return_value=mock_client
        ):
            result = await grouper.group_messages_with_context(
                messages, "test-user", mock_db
            )

        assert len(result) == 1
        assert result[0].conversation_type == "thread"
        assert result[0].thread_context is not None

    @pytest.mark.asyncio
    async def test_group_with_context_sets_first_run_mode(self):
        """First-run thread uses 'full' summarization mode."""
        grouper = DigestGrouper()
        messages = [
            create_classification("C123", "T1", "U1", "100.1"),
        ]

        mock_client = AsyncMock()
        mock_client.conversations_replies = AsyncMock(
            return_value={
                "messages": [
                    {"ts": "100.1", "user": "U1", "text": "Message"},
                ]
            }
        )

        mock_db = AsyncMock()

        with patch.object(
            grouper, "_get_user_client", return_value=mock_client
        ):
            result = await grouper.group_messages_with_context(
                messages, "test-user", mock_db
            )

        assert len(result) == 1
        assert result[0].summarization_mode == "full"

    @pytest.mark.asyncio
    async def test_group_with_context_sets_incremental_mode(self):
        """Non-first-run thread uses 'thread_incremental' mode."""
        grouper = DigestGrouper()
        messages = [
            create_classification("C123", "T1", "U1", "100.2"),
        ]

        mock_client = AsyncMock()
        mock_client.conversations_replies = AsyncMock(
            return_value={
                "messages": [
                    {"ts": "100.0", "user": "U2", "text": "Parent"},
                    {"ts": "100.1", "user": "U3", "text": "Earlier reply"},
                    {"ts": "100.2", "user": "U1", "text": "New reply"},
                ]
            }
        )

        mock_db = AsyncMock()

        with patch.object(
            grouper, "_get_user_client", return_value=mock_client
        ):
            result = await grouper.group_messages_with_context(
                messages, "test-user", mock_db
            )

        assert len(result) == 1
        assert result[0].summarization_mode == "thread_incremental"

    @pytest.mark.asyncio
    async def test_group_with_context_no_client_returns_basic_groups(self):
        """Returns basic groups when no user client available."""
        grouper = DigestGrouper()
        messages = [
            create_classification("C123", "T1", "U1", "100.1"),
        ]

        mock_db = AsyncMock()

        with patch.object(
            grouper, "_get_user_client", return_value=None
        ):
            result = await grouper.group_messages_with_context(
                messages, "test-user", mock_db
            )

        assert len(result) == 1
        assert result[0].thread_context is None
