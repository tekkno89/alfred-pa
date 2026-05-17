"""Tests for TriageEnrichmentService."""

from unittest.mock import AsyncMock

import pytest

from app.services.triage_enrichment import generate_slack_permalink


class TestGenerateSlackPermalink:
    def test_basic_permalink(self):
        result = generate_slack_permalink(
            workspace_domain="myworkspace",
            channel_id="C12345",
            message_ts="1234567890.123456",
        )
        assert (
            result == "https://myworkspace.slack.com/archives/C12345/p1234567890123456"
        )

    def test_permalink_with_thread(self):
        result = generate_slack_permalink(
            workspace_domain="myworkspace",
            channel_id="C12345",
            message_ts="1234567890.123456",
            thread_ts="1234567890.000001",
        )
        assert "thread_ts=1234567890000001" in result
        assert "cid=C12345" in result

    def test_permalink_same_thread_ts(self):
        """When thread_ts == message_ts, no thread param needed."""
        result = generate_slack_permalink(
            workspace_domain="myworkspace",
            channel_id="C12345",
            message_ts="1234567890.123456",
            thread_ts="1234567890.123456",
        )
        assert "thread_ts" not in result

    def test_permalink_no_workspace(self):
        result = generate_slack_permalink(
            workspace_domain=None,
            channel_id="C12345",
            message_ts="1234567890.123456",
        )
        assert result is None


class TestResolveUserNamesBatch:
    """Tests for resolve_user_names_batch function."""

    @pytest.mark.asyncio
    async def test_returns_names_for_all_ids(self):
        """Should return names for all requested user IDs."""
        from app.services.triage_enrichment import resolve_user_names_batch

        mock_slack = AsyncMock()
        mock_slack.get_user_info = AsyncMock(
            side_effect=lambda uid: {
                "U1": {"real_name": "Alice", "profile": {}, "name": "alice"},
                "U2": {"real_name": "Bob", "profile": {}, "name": "bob"},
            }.get(uid, {})
        )

        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=None)
        mock_redis.set = AsyncMock()

        result = await resolve_user_names_batch(mock_slack, mock_redis, {"U1", "U2"})

        assert result["U1"] == "Alice"
        assert result["U2"] == "Bob"

    @pytest.mark.asyncio
    async def test_uses_cache_on_hit(self):
        """Should use cached names and not call Slack API."""
        from app.services.triage_enrichment import resolve_user_names_batch

        mock_slack = AsyncMock()
        mock_slack.get_user_info = AsyncMock()

        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(
            side_effect=lambda key: "CachedName" if "U1" in key else None
        )
        mock_redis.set = AsyncMock()

        result = await resolve_user_names_batch(mock_slack, mock_redis, {"U1"})

        assert result["U1"] == "CachedName"
        mock_slack.get_user_info.assert_not_called()

    @pytest.mark.asyncio
    async def test_writes_to_cache_on_miss(self):
        """Should write resolved names to cache."""
        from app.services.triage_enrichment import resolve_user_names_batch

        mock_slack = AsyncMock()
        mock_slack.get_user_info = AsyncMock(
            return_value={"real_name": "Charlie", "profile": {}, "name": "charlie"}
        )

        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=None)
        mock_redis.set = AsyncMock()

        await resolve_user_names_batch(mock_slack, mock_redis, {"U3"})

        mock_redis.set.assert_called_once()
        call_args = mock_redis.set.call_args
        assert "slack:user_name:U3" in call_args[0][0]
        assert call_args[0][1] == "Charlie"
        assert call_args[1]["ex"] == 86400

    @pytest.mark.asyncio
    async def test_fallback_chain_real_name_first(self):
        """Should prefer real_name over profile.display_name."""
        from app.services.triage_enrichment import resolve_user_names_batch

        mock_slack = AsyncMock()
        mock_slack.get_user_info = AsyncMock(
            return_value={
                "real_name": "Real Name",
                "profile": {"display_name": "Display Name"},
                "name": "username",
            }
        )

        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=None)
        mock_redis.set = AsyncMock()

        result = await resolve_user_names_batch(mock_slack, mock_redis, {"U1"})

        assert result["U1"] == "Real Name"

    @pytest.mark.asyncio
    async def test_fallback_chain_display_name_second(self):
        """Should use profile.display_name if real_name is missing."""
        from app.services.triage_enrichment import resolve_user_names_batch

        mock_slack = AsyncMock()
        mock_slack.get_user_info = AsyncMock(
            return_value={
                "profile": {"display_name": "Display Name"},
                "name": "username",
            }
        )

        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=None)
        mock_redis.set = AsyncMock()

        result = await resolve_user_names_batch(mock_slack, mock_redis, {"U1"})

        assert result["U1"] == "Display Name"

    @pytest.mark.asyncio
    async def test_fallback_chain_name_third(self):
        """Should use name field if real_name and display_name are missing."""
        from app.services.triage_enrichment import resolve_user_names_batch

        mock_slack = AsyncMock()
        mock_slack.get_user_info = AsyncMock(return_value={"name": "username"})

        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=None)
        mock_redis.set = AsyncMock()

        result = await resolve_user_names_batch(mock_slack, mock_redis, {"U1"})

        assert result["U1"] == "username"

    @pytest.mark.asyncio
    async def test_fallback_to_user_id(self):
        """Should fall back to user_id if all fields missing."""
        from app.services.triage_enrichment import resolve_user_names_batch

        mock_slack = AsyncMock()
        mock_slack.get_user_info = AsyncMock(side_effect=Exception("API error"))

        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=None)
        mock_redis.set = AsyncMock()

        result = await resolve_user_names_batch(mock_slack, mock_redis, {"U1"})

        assert result["U1"] == "U1"

    @pytest.mark.asyncio
    async def test_empty_user_ids(self):
        """Should return empty dict for empty input."""
        from app.services.triage_enrichment import resolve_user_names_batch

        mock_slack = AsyncMock()
        mock_redis = AsyncMock()

        result = await resolve_user_names_batch(mock_slack, mock_redis, set())

        assert result == {}


class TestResolveUserName:
    """Tests for resolve_user_name single-user wrapper."""

    @pytest.mark.asyncio
    async def test_calls_through_batch(self):
        """Single-user resolver should call through batch internally."""
        from app.services.triage_enrichment import resolve_user_name

        mock_slack = AsyncMock()
        mock_slack.get_user_info = AsyncMock(
            return_value={"real_name": "Alice", "profile": {}, "name": "alice"}
        )

        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=None)
        mock_redis.set = AsyncMock()

        result = await resolve_user_name(mock_slack, mock_redis, "U1")

        assert result == "Alice"

    @pytest.mark.asyncio
    async def test_returns_user_id_on_failure(self):
        """Should return user_id if resolution fails."""
        from app.services.triage_enrichment import resolve_user_name

        mock_slack = AsyncMock()
        mock_slack.get_user_info = AsyncMock(side_effect=Exception("API error"))

        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=None)
        mock_redis.set = AsyncMock()

        result = await resolve_user_name(mock_slack, mock_redis, "U123")

        assert result == "U123"


class TestLearningSignalsEnrichment:
    """Tests for learning signal fetching in enrich method."""

    @pytest.mark.asyncio
    async def test_few_shot_examples_populated(self):
        """enrich should populate few_shot_examples from LearnedExampleRetriever."""
        from unittest.mock import MagicMock, patch
        from app.services.triage_enrichment import TriageEnrichmentService
        from app.services.learned_example_retriever import LearnedExample

        mock_db = AsyncMock()
        service = TriageEnrichmentService(mock_db)

        mock_db.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=lambda: None))

        mock_example = LearnedExample(
            original_abstract="Test",
            correct_action="notify_now",
            feedback_reason="Urgent",
            similarity=0.9,
        )

        with patch(
            "app.services.learned_example_retriever.LearnedExampleRetriever"
        ) as mock_retriever_class:
            mock_retriever = AsyncMock()
            mock_retriever.retrieve_examples = AsyncMock(return_value=[mock_example])
            mock_retriever_class.return_value = mock_retriever

            with patch(
                "app.services.topic_affinity_service.TopicAffinityService"
            ) as mock_topic_class:
                mock_topic = AsyncMock()
                mock_topic.get_biases = AsyncMock(return_value=[])
                mock_topic_class.return_value = mock_topic

                payload = await service.enrich(
                    user_id="u1",
                    event_type="channel",
                    channel_id="C123",
                    sender_slack_id="U123",
                    message_ts="1234567890.123456",
                    thread_ts=None,
                    message_text="Test message",
                )

                assert len(payload.few_shot_examples) == 1
                assert payload.few_shot_examples[0].correct_action == "notify_now"

    @pytest.mark.asyncio
    async def test_sender_distribution_populated(self):
        """enrich should populate sender_action_distribution from SenderActionDistribution."""
        from unittest.mock import MagicMock, patch
        from app.services.triage_enrichment import TriageEnrichmentService

        mock_db = AsyncMock()
        service = TriageEnrichmentService(mock_db)

        mock_dist = MagicMock()
        mock_dist.sample_count = 15
        mock_dist.action_distribution = {
            "notify_now": 0.5,
            "summarize_next": 0.3,
            "summarize_eod": 0.1,
            "ignore": 0.1,
        }

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_dist
        mock_db.execute = AsyncMock(return_value=mock_result)

        with patch(
            "app.services.learned_example_retriever.LearnedExampleRetriever"
        ) as mock_retriever_class:
            mock_retriever = AsyncMock()
            mock_retriever.retrieve_examples = AsyncMock(return_value=[])
            mock_retriever_class.return_value = mock_retriever

            with patch(
                "app.services.topic_affinity_service.TopicAffinityService"
            ) as mock_topic_class:
                mock_topic = AsyncMock()
                mock_topic.get_biases = AsyncMock(return_value=[])
                mock_topic_class.return_value = mock_topic

                payload = await service.enrich(
                    user_id="u1",
                    event_type="channel",
                    channel_id="C123",
                    sender_slack_id="U123",
                    message_ts="1234567890.123456",
                    thread_ts=None,
                    message_text="Test message",
                )

                assert payload.sender_action_distribution is not None
                assert payload.sender_action_distribution["notify_now"] == 0.5

    @pytest.mark.asyncio
    async def test_topic_biases_populated(self):
        """enrich should populate topic_biases from TopicAffinityService."""
        from unittest.mock import MagicMock, patch
        from app.services.triage_enrichment import TriageEnrichmentService
        from app.services.topic_affinity_service import KeywordBias

        mock_db = AsyncMock()
        service = TriageEnrichmentService(mock_db)

        mock_db.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=lambda: None))

        mock_bias = KeywordBias(
            keyword="urgent",
            weight=0.8,
            source_category="public",
        )

        with patch(
            "app.services.learned_example_retriever.LearnedExampleRetriever"
        ) as mock_retriever_class:
            mock_retriever = AsyncMock()
            mock_retriever.retrieve_examples = AsyncMock(return_value=[])
            mock_retriever_class.return_value = mock_retriever

            with patch(
                "app.services.topic_affinity_service.TopicAffinityService"
            ) as mock_topic_class:
                mock_topic = AsyncMock()
                mock_topic.get_biases = AsyncMock(return_value=[mock_bias])
                mock_topic_class.return_value = mock_topic

                payload = await service.enrich(
                    user_id="u1",
                    event_type="channel",
                    channel_id="C123",
                    sender_slack_id="U123",
                    message_ts="1234567890.123456",
                    thread_ts=None,
                    message_text="Test message",
                )

                assert len(payload.topic_biases) == 1
                assert payload.topic_biases[0]["keyword"] == "urgent"

    @pytest.mark.asyncio
    async def test_learning_signals_default_on_exception(self):
        """enrich should default learning signals to empty/None on exception."""
        from unittest.mock import MagicMock, patch
        from app.services.triage_enrichment import TriageEnrichmentService

        mock_db = AsyncMock()
        service = TriageEnrichmentService(mock_db)

        mock_settings_result = MagicMock()
        mock_settings_result.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(return_value=mock_settings_result)

        with patch(
            "app.services.learned_example_retriever.LearnedExampleRetriever"
        ) as mock_retriever_class:
            mock_retriever = AsyncMock()
            mock_retriever.retrieve_examples = AsyncMock(side_effect=Exception("Error"))
            mock_retriever_class.return_value = mock_retriever

            with patch(
                "app.services.topic_affinity_service.TopicAffinityService"
            ) as mock_topic_class:
                mock_topic = AsyncMock()
                mock_topic.get_biases = AsyncMock(side_effect=Exception("Error"))
                mock_topic_class.return_value = mock_topic

                payload = await service.enrich(
                    user_id="u1",
                    event_type="channel",
                    channel_id="C123",
                    sender_slack_id="U123",
                    message_ts="1234567890.123456",
                    thread_ts=None,
                    message_text="Test message",
                )

                assert payload.few_shot_examples == []
                assert payload.sender_action_distribution is None
                assert payload.topic_biases == []
