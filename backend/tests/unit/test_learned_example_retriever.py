"""Unit tests for LearnedExampleRetriever."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.learned_example_retriever import (
    LearnedExample,
    LearnedExampleRetriever,
)


@pytest.fixture
def mock_db():
    db = AsyncMock()
    db.add = MagicMock()
    return db


@pytest.fixture
def retriever(mock_db):
    return LearnedExampleRetriever(mock_db)


class TestLearnedExampleRetriever:
    @pytest.mark.asyncio
    async def test_retrieve_examples_returns_similar(self, retriever, mock_db):
        """retrieve_examples should return similar past corrections."""
        mock_result = MagicMock()
        mock_result.all.return_value = []
        mock_db.execute.return_value = mock_result

        with patch(
            "app.services.learned_example_retriever.get_embedding_provider"
        ) as mock_provider:
            mock_embedding_provider = MagicMock()
            mock_embedding_provider.embed_text = AsyncMock(return_value=[0.1] * 768)
            mock_provider.return_value = mock_embedding_provider

            examples = await retriever.retrieve_examples(
                user_id="u1",
                channel_id="C123",
                sender_slack_id="U123",
                message_text="Test message",
            )

            assert isinstance(examples, list)

    @pytest.mark.asyncio
    async def test_retrieve_examples_uses_filters(self, retriever, mock_db):
        """retrieve_examples should filter by channel and sender when provided."""
        mock_result = MagicMock()
        mock_result.all.return_value = []
        mock_db.execute.return_value = mock_result

        with patch(
            "app.services.learned_example_retriever.get_embedding_provider"
        ) as mock_provider:
            mock_embedding_provider = MagicMock()
            mock_embedding_provider.embed_text = AsyncMock(return_value=[0.1] * 768)
            mock_provider.return_value = mock_embedding_provider

            await retriever.retrieve_examples(
                user_id="u1",
                channel_id="C123",
                sender_slack_id="U123",
                message_text="Test message",
                top_k=3,
            )

            mock_db.execute.assert_called_once()
            call_arg = mock_db.execute.call_args[0][0]
            compiled = str(call_arg.compile())
            assert "C123" in compiled or "channel_id" in compiled.lower()

    @pytest.mark.asyncio
    async def test_retrieve_examples_returns_learned_examples(self, retriever, mock_db):
        """retrieve_examples should return LearnedExample objects."""
        mock_feedback_emb = MagicMock()
        mock_feedback_emb.embedding_vector.cosine_distance.return_value = 0.2

        mock_feedback = MagicMock()
        mock_feedback.correct_action = "notify_now"
        mock_feedback.feedback_text = "This was urgent"

        mock_classification = MagicMock()
        mock_classification.abstract = "Test abstract"

        mock_result = MagicMock()
        mock_result.all.return_value = [
            (mock_feedback_emb, mock_feedback, mock_classification)
        ]
        mock_db.execute.return_value = mock_result

        with patch(
            "app.services.learned_example_retriever.get_embedding_provider"
        ) as mock_provider:
            mock_embedding_provider = MagicMock()
            mock_embedding_provider.embed_text = AsyncMock(return_value=[0.1] * 768)
            mock_provider.return_value = mock_embedding_provider

            examples = await retriever.retrieve_examples(
                user_id="u1",
                channel_id="C123",
                sender_slack_id="U123",
                message_text="Test message",
            )

            assert len(examples) == 1
            assert isinstance(examples[0], LearnedExample)
            assert examples[0].correct_action == "notify_now"
            assert examples[0].feedback_reason == "This was urgent"
            assert examples[0].original_abstract == "Test abstract"

    @pytest.mark.asyncio
    async def test_store_correction_embedding(self, retriever, mock_db):
        """store_correction_embedding should compute and store embedding."""
        with patch(
            "app.services.learned_example_retriever.get_embedding_provider"
        ) as mock_provider:
            mock_embedding_provider = MagicMock()
            mock_embedding_provider.embed_text = AsyncMock(return_value=[0.1] * 768)
            mock_provider.return_value = mock_embedding_provider

            result = await retriever.store_correction_embedding(
                feedback_id="fb1",
                message_text="Test message",
            )

            mock_db.add.assert_called_once()
            mock_db.commit.assert_called_once()
            mock_db.refresh.assert_called_once()

    def test_learned_example_dataclass(self):
        """LearnedExample should have expected fields."""
        example = LearnedExample(
            original_abstract="Test abstract",
            correct_action="notify_now",
            feedback_reason="This was urgent",
            similarity=0.85,
        )

        assert example.correct_action == "notify_now"
        assert example.similarity == 0.85
        assert example.original_abstract == "Test abstract"
        assert example.feedback_reason == "This was urgent"

    def test_learned_example_optional_feedback_reason(self):
        """LearnedExample should allow None for feedback_reason."""
        example = LearnedExample(
            original_abstract="Test abstract",
            correct_action="summarize_next",
            feedback_reason=None,
            similarity=0.5,
        )

        assert example.feedback_reason is None
