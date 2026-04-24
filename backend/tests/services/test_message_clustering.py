"""Tests for message_clustering service."""

import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch
import uuid

from app.services.message_clustering import (
    MessageCluster,
    parse_ts,
    find_split_point,
    partition_messages,
    cluster_messages_with_llm,
    _fallback_singleton_clusters,
    MAX_CLUSTERING_BATCH_SIZE,
    CONVERSATION_GAP_THRESHOLD_MINUTES,
)
from app.db.models.triage import TriageClassification


def create_classification(
    message_ts: str,
    sender_id: str = "U1",
    sender_name: str = "User1",
    abstract: str = "Test message",
    channel_id: str = "C123",
) -> TriageClassification:
    """Helper to create a TriageClassification for testing."""
    return TriageClassification(
        id=str(uuid.uuid4()),
        user_id="test-user",
        sender_slack_id=sender_id,
        sender_name=sender_name,
        channel_id=channel_id,
        channel_name="test-channel",
        message_ts=message_ts,
        thread_ts=None,
        priority_level="p2",
        confidence=0.9,
        classification_path="channel",
        created_at=datetime.utcnow(),
        abstract=abstract,
    )


class TestParseTs:
    """Tests for parse_ts function."""

    def test_parse_basic_timestamp(self):
        """Parse a basic Slack timestamp."""
        result = parse_ts("1234567890.001234")
        assert isinstance(result, datetime)

    def test_parse_timestamp_without_microseconds(self):
        """Parse timestamp without microseconds."""
        result = parse_ts("1234567890")
        assert isinstance(result, datetime)

    def test_parse_preserves_order(self):
        """Earlier timestamps parse to earlier datetimes."""
        t1 = parse_ts("100.1")
        t2 = parse_ts("200.1")
        assert t1 < t2


class TestFindSplitPoint:
    """Tests for find_split_point function."""

    def test_single_message(self):
        """Single message returns 1."""
        messages = [create_classification("100.1")]
        result = find_split_point(messages)
        assert result == 1

    def test_no_gap_returns_midpoint(self):
        """No gap returns midpoint."""
        messages = [
            create_classification("100.1"),
            create_classification("100.2"),
            create_classification("100.3"),
            create_classification("100.4"),
        ]
        result = find_split_point(messages)
        assert result == 2

    def test_finds_large_gap(self):
        """Finds gap >= threshold minutes."""
        base_ts = 1000000000.0
        messages = [
            create_classification(f"{base_ts:.6f}"),
            create_classification(f"{(base_ts + 60):.6f}"),
            create_classification(f"{(base_ts + 120):.6f}"),
            create_classification(f"{(base_ts + 1200):.6f}"),
        ]
        result = find_split_point(messages, gap_threshold_minutes=10)
        assert result == 3

    def test_picks_gap_closest_to_midpoint(self):
        """When multiple gaps, picks one closest to midpoint."""
        base_ts = 1000000000.0
        messages = []
        for i in range(4):
            messages.append(create_classification(f"{(base_ts + i * 60):.6f}"))
        for i in range(4):
            messages.append(create_classification(f"{(base_ts + 3600 + i * 60):.6f}"))

        result = find_split_point(messages, gap_threshold_minutes=10)
        assert result in [3, 4]

    def test_empty_messages(self):
        """Empty list returns 0."""
        result = find_split_point([])
        assert result == 0


class TestPartitionMessages:
    """Tests for partition_messages function."""

    def test_empty_messages(self):
        """Empty input returns empty list."""
        result = partition_messages([])
        assert result == []

    def test_small_batch_unchanged(self):
        """Messages <= max_batch_size stay together."""
        messages = [create_classification(f"{i}.0") for i in range(10)]
        result = partition_messages(messages, max_batch_size=40)
        assert len(result) == 1
        assert len(result[0]) == 10

    def test_exactly_max_batch_size(self):
        """Exactly max_batch_size stays together."""
        messages = [create_classification(f"{i}.0") for i in range(40)]
        result = partition_messages(messages, max_batch_size=40)
        assert len(result) == 1
        assert len(result[0]) == 40

    def test_splits_at_midpoint_no_gap(self):
        """Messages > max split at midpoint when no gap."""
        messages = [create_classification(f"{i}.0") for i in range(41)]
        result = partition_messages(messages, max_batch_size=40)
        assert len(result) == 2
        assert len(result[0]) <= 40
        assert len(result[1]) <= 40
        total = sum(len(b) for b in result)
        assert total == 41

    def test_respects_gap_boundary(self):
        """Splits at gap when available."""
        base_ts = 1000000000.0
        messages = []
        for i in range(25):
            messages.append(create_classification(f"{(base_ts + i * 60):.6f}"))
        for i in range(25):
            messages.append(create_classification(f"{(base_ts + 7200 + i * 60):.6f}"))

        result = partition_messages(messages, max_batch_size=40)
        assert len(result) == 2

    def test_large_batch_multiple_splits(self):
        """Very large batches get multiple splits."""
        messages = [create_classification(f"{i}.0") for i in range(100)]
        result = partition_messages(messages, max_batch_size=40)
        assert len(result) >= 3
        for batch in result:
            assert len(batch) <= 40
        total = sum(len(b) for b in result)
        assert total == 100

    def test_messages_sorted_by_ts(self):
        """Output batches are sorted by timestamp."""
        messages = [
            create_classification("300.0"),
            create_classification("100.0"),
            create_classification("200.0"),
        ]
        result = partition_messages(messages, max_batch_size=40)
        ts_order = [m.message_ts for m in result[0]]
        assert ts_order == ["100.0", "200.0", "300.0"]


class TestClusterMessagesWithLlm:
    """Tests for cluster_messages_with_llm function."""

    @pytest.mark.asyncio
    async def test_single_message_no_llm_call(self):
        """Single message returns singleton cluster without LLM call."""
        msg = create_classification("100.0")
        result = await cluster_messages_with_llm([msg])

        assert len(result) == 1
        assert result[0].cluster_id == "c1"
        assert result[0].message_ids == [msg.id]
        assert result[0].messages == [msg]

    @pytest.mark.asyncio
    async def test_empty_messages(self):
        """Empty input returns empty list."""
        result = await cluster_messages_with_llm([])
        assert result == []

    @pytest.mark.asyncio
    async def test_llm_clusters_messages(self):
        """LLM successfully clusters messages."""
        messages = [
            create_classification("100.0", sender_id="U1", sender_name="Alice"),
            create_classification("100.1", sender_id="U2", sender_name="Bob"),
        ]

        mock_response = """
        {
            "clusters": [
                {"cluster_id": "c1", "message_ids": ["%s", "%s"]}
            ]
        }
        """ % (messages[0].id, messages[1].id)

        with patch("app.core.llm.get_llm_provider") as mock_get_provider:
            mock_llm = AsyncMock()
            mock_llm.generate = AsyncMock(return_value=mock_response)
            mock_get_provider.return_value = mock_llm

            result = await cluster_messages_with_llm(messages)

            assert len(result) == 1
            assert len(result[0].messages) == 2

    @pytest.mark.asyncio
    async def test_llm_returns_separate_clusters(self):
        """LLM can return separate clusters."""
        messages = [
            create_classification(
                "100.0", sender_id="U1", abstract="Project A discussion"
            ),
            create_classification(
                "100.1", sender_id="U2", abstract="Project B discussion"
            ),
        ]

        mock_response = """
        {
            "clusters": [
                {"cluster_id": "c1", "message_ids": ["%s"]},
                {"cluster_id": "c2", "message_ids": ["%s"]}
            ]
        }
        """ % (messages[0].id, messages[1].id)

        with patch("app.core.llm.get_llm_provider") as mock_get_provider:
            mock_llm = AsyncMock()
            mock_llm.generate = AsyncMock(return_value=mock_response)
            mock_get_provider.return_value = mock_llm

            result = await cluster_messages_with_llm(messages)

            assert len(result) == 2
            assert result[0].cluster_id == "c1"
            assert result[1].cluster_id == "c2"

    @pytest.mark.asyncio
    async def test_malformed_json_fallback(self):
        """Malformed JSON falls back to singleton clusters."""
        messages = [
            create_classification("100.0"),
            create_classification("100.1"),
        ]

        with patch("app.core.llm.get_llm_provider") as mock_get_provider:
            mock_llm = AsyncMock()
            mock_llm.generate = AsyncMock(return_value="not valid json {{{")
            mock_get_provider.return_value = mock_llm

            result = await cluster_messages_with_llm(messages)

            assert len(result) == 2
            assert all(len(c.messages) == 1 for c in result)

    @pytest.mark.asyncio
    async def test_llm_error_fallback(self):
        """LLM error falls back to singleton clusters."""
        messages = [
            create_classification("100.0"),
            create_classification("100.1"),
        ]

        with patch("app.core.llm.get_llm_provider") as mock_get_provider:
            mock_llm = AsyncMock()
            mock_llm.generate = AsyncMock(side_effect=Exception("LLM error"))
            mock_get_provider.return_value = mock_llm

            result = await cluster_messages_with_llm(messages)

            assert len(result) == 2
            assert all(len(c.messages) == 1 for c in result)

    @pytest.mark.asyncio
    async def test_missing_message_id_in_cluster(self):
        """Handles missing message IDs gracefully."""
        messages = [
            create_classification("100.0"),
            create_classification("100.1"),
        ]

        mock_response = (
            """
        {
            "clusters": [
                {"cluster_id": "c1", "message_ids": ["%s", "nonexistent-id"]}
            ]
        }
        """
            % messages[0].id
        )

        with patch("app.core.llm.get_llm_provider") as mock_get_provider:
            mock_llm = AsyncMock()
            mock_llm.generate = AsyncMock(return_value=mock_response)
            mock_get_provider.return_value = mock_llm

            result = await cluster_messages_with_llm(messages)

            assert len(result) == 2

    @pytest.mark.asyncio
    async def test_orphan_messages_get_own_cluster(self):
        """Messages not in any cluster get their own cluster."""
        messages = [
            create_classification("100.0"),
            create_classification("100.1"),
            create_classification("100.2"),
        ]

        mock_response = (
            """
        {
            "clusters": [
                {"cluster_id": "c1", "message_ids": ["%s"]}
            ]
        }
        """
            % messages[0].id
        )

        with patch("app.core.llm.get_llm_provider") as mock_get_provider:
            mock_llm = AsyncMock()
            mock_llm.generate = AsyncMock(return_value=mock_response)
            mock_get_provider.return_value = mock_llm

            result = await cluster_messages_with_llm(messages)

            assert len(result) == 3

    @pytest.mark.asyncio
    async def test_uses_user_name_resolver(self):
        """Uses provided user name resolver for display names."""
        messages = [
            create_classification("100.0", sender_id="U1", sender_name="Alice"),
            create_classification("100.1", sender_id="U2", sender_name="Bob"),
        ]

        name_resolver = {"U1": "DisplayAlice", "U2": "DisplayBob"}

        mock_response = """
        {
            "clusters": [
                {"cluster_id": "c1", "message_ids": ["%s", "%s"]}
            ]
        }
        """ % (messages[0].id, messages[1].id)

        with patch("app.core.llm.get_llm_provider") as mock_get_provider:
            mock_llm = AsyncMock()
            mock_llm.generate = AsyncMock(return_value=mock_response)
            mock_get_provider.return_value = mock_llm

            await cluster_messages_with_llm(messages, user_name_resolver=name_resolver)

            call_args = mock_llm.generate.call_args
            assert call_args is not None
            prompt = call_args[1]["messages"][0].content
            assert "DisplayAlice" in prompt
            assert "DisplayBob" in prompt


class TestFallbackSingletonClusters:
    """Tests for _fallback_singleton_clusters function."""

    def test_creates_singletons(self):
        """Each message becomes its own cluster."""
        messages = [
            create_classification("100.0"),
            create_classification("100.1"),
            create_classification("100.2"),
        ]
        result = _fallback_singleton_clusters(messages)

        assert len(result) == 3
        assert all(len(c.messages) == 1 for c in result)
        assert all(len(c.message_ids) == 1 for c in result)

    def test_cluster_ids_unique(self):
        """Each cluster gets unique ID."""
        messages = [
            create_classification("100.0"),
            create_classification("100.1"),
        ]
        result = _fallback_singleton_clusters(messages)

        ids = [c.cluster_id for c in result]
        assert len(ids) == len(set(ids))

    def test_empty_input(self):
        """Empty input returns empty list."""
        result = _fallback_singleton_clusters([])
        assert result == []


class TestConstants:
    """Tests for module constants."""

    def test_max_batch_size(self):
        """Batch size constant is 40."""
        assert MAX_CLUSTERING_BATCH_SIZE == 40

    def test_gap_threshold(self):
        """Gap threshold constant is 10 minutes."""
        assert CONVERSATION_GAP_THRESHOLD_MINUTES == 10
