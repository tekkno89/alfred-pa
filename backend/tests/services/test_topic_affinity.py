"""Unit tests for TopicAffinityService."""

import json
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.topic_affinity_service import (
    KeywordBias,
    TopicAffinityService,
    HALF_LIFE_DAYS,
)
from app.db.models.triage import TopicAffinity


@pytest.fixture
def mock_db():
    """Create mock database session."""
    return AsyncMock()


@pytest.fixture
def service(mock_db):
    """Create service with mock db."""
    return TopicAffinityService(mock_db)


class TestExtractKeywords:
    async def test_extract_keywords_success(self, service):
        mock_provider = AsyncMock()
        mock_provider.generate.return_value = '["python", "api", "backend"]'

        with patch(
            "app.services.topic_affinity_service.get_llm_provider",
            return_value=mock_provider,
        ):
            result = await service.extract_keywords("Message about python API development")

        assert result == ["python", "api", "backend"]
        mock_provider.generate.assert_called_once()

    async def test_extract_keywords_max_five(self, service):
        mock_provider = AsyncMock()
        mock_provider.generate.return_value = '["a", "b", "c", "d", "e", "f", "g"]'

        with patch(
            "app.services.topic_affinity_service.get_llm_provider",
            return_value=mock_provider,
        ):
            result = await service.extract_keywords("Message text")

        assert len(result) == 5
        assert result == ["a", "b", "c", "d", "e"]

    async def test_extract_keywords_lowercase(self, service):
        mock_provider = AsyncMock()
        mock_provider.generate.return_value = '["Python", "API", "BACKEND"]'

        with patch(
            "app.services.topic_affinity_service.get_llm_provider",
            return_value=mock_provider,
        ):
            result = await service.extract_keywords("Message text")

        assert result == ["python", "api", "backend"]

    async def test_extract_keywords_invalid_json(self, service):
        mock_provider = AsyncMock()
        mock_provider.generate.return_value = "not valid json"

        with patch(
            "app.services.topic_affinity_service.get_llm_provider",
            return_value=mock_provider,
        ):
            result = await service.extract_keywords("Message text")

        assert result == []

    async def test_extract_keywords_llm_error(self, service):
        mock_provider = AsyncMock()
        mock_provider.generate.side_effect = Exception("LLM error")

        with patch(
            "app.services.topic_affinity_service.get_llm_provider",
            return_value=mock_provider,
        ):
            result = await service.extract_keywords("Message text")

        assert result == []

    async def test_extract_keywords_truncates_long_message(self, service):
        mock_provider = AsyncMock()
        mock_provider.generate.return_value = '["test"]'
        long_message = "x" * 1000

        with patch(
            "app.services.topic_affinity_service.get_llm_provider",
            return_value=mock_provider,
        ):
            await service.extract_keywords(long_message)

        call_args = mock_provider.generate.call_args
        user_message = call_args[1]["messages"][1].content
        assert len(user_message) == 500


class TestUpdateAffinity:
    async def test_update_affinity_creates_new(self, service, mock_db):
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        await service.update_affinity(
            user_id="user-123",
            keywords=["python", "api"],
            source_category="public",
            is_positive=True,
        )

        assert mock_db.add.call_count == 2
        mock_db.commit.assert_called_once()

    async def test_update_affinity_updates_existing(self, service, mock_db):
        existing = TopicAffinity(
            user_id="user-123",
            keyword="python",
            weight=0.5,
            source_category="public",
        )
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = existing
        mock_db.execute.return_value = mock_result

        await service.update_affinity(
            user_id="user-123",
            keywords=["python"],
            source_category="public",
            is_positive=True,
        )

        # weight = 0.5 * 0.9 + 0.2 = 0.65
        assert existing.weight == pytest.approx(0.65)
        mock_db.commit.assert_called_once()

    async def test_update_affinity_negative_signal(self, service, mock_db):
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        await service.update_affinity(
            user_id="user-123",
            keywords=["spam"],
            source_category="public",
            is_positive=False,
        )

        mock_db.add.assert_called_once()
        added = mock_db.add.call_args[0][0]
        assert added.weight == -0.1

    async def test_update_affinity_clamps_weight(self, service, mock_db):
        existing = TopicAffinity(
            user_id="user-123",
            keyword="python",
            weight=0.95,
            source_category="public",
        )
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = existing
        mock_db.execute.return_value = mock_result

        await service.update_affinity(
            user_id="user-123",
            keywords=["python"],
            source_category="public",
            is_positive=True,
        )

        # weight = 0.95 * 0.9 + 0.2 = 1.055, clamped to 1.0
        assert existing.weight == pytest.approx(1.0)


class TestGetBiases:
    async def test_get_biases_with_decay(self, service, mock_db):
        from datetime import timezone
        now = datetime.now(timezone.utc)
        affinity1 = TopicAffinity(
            user_id="user-123",
            keyword="python",
            weight=0.8,
            source_category="public",
            last_updated=now - timedelta(days=30),  # 30 days old
        )
        affinity2 = TopicAffinity(
            user_id="user-123",
            keyword="spam",
            weight=-0.5,
            source_category="public",
            last_updated=now,  # fresh
        )

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [affinity1, affinity2]
        mock_db.execute.return_value = mock_result

        biases = await service.get_biases("user-123")

        assert len(biases) == 2
        # affinity1: 0.8 * 0.5 (half-life decay) = 0.4
        assert biases[0].keyword == "python"
        assert biases[0].weight == pytest.approx(0.4, abs=0.01)
        # affinity2: -0.5 * 1.0 (no decay) = -0.5
        assert biases[1].keyword == "spam"
        assert biases[1].weight == pytest.approx(-0.5, abs=0.01)

    async def test_get_biases_filters_low_weight(self, service, mock_db):
        from datetime import timezone
        now = datetime.now(timezone.utc)
        affinity = TopicAffinity(
            user_id="user-123",
            keyword="python",
            weight=0.05,  # Below 0.1 threshold
            source_category="public",
            last_updated=now,
        )

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [affinity]
        mock_db.execute.return_value = mock_result

        biases = await service.get_biases("user-123")

        assert len(biases) == 0

    async def test_get_biases_returns_empty_list(self, service, mock_db):
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute.return_value = mock_result

        biases = await service.get_biases("user-123")

        assert biases == []


class TestDeleteKeyword:
    async def test_delete_keyword_found(self, service, mock_db):
        mock_result = MagicMock()
        mock_result.rowcount = 1
        mock_db.execute.return_value = mock_result

        result = await service.delete_keyword("user-123", "python")

        assert result is True
        mock_db.commit.assert_called_once()

    async def test_delete_keyword_not_found(self, service, mock_db):
        mock_result = MagicMock()
        mock_result.rowcount = 0
        mock_db.execute.return_value = mock_result

        result = await service.delete_keyword("user-123", "nonexistent")

        assert result is False


class TestDeleteByCategory:
    async def test_delete_by_category(self, service, mock_db):
        mock_result = MagicMock()
        mock_result.rowcount = 5
        mock_db.execute.return_value = mock_result

        count = await service.delete_by_category("user-123", "dm")

        assert count == 5
        mock_db.commit.assert_called_once()


class TestKeywordBias:
    def test_keyword_bias_dataclass(self):
        bias = KeywordBias(
            keyword="python",
            weight=0.5,
            source_category="public",
        )
        assert bias.keyword == "python"
        assert bias.weight == 0.5
        assert bias.source_category == "public"
