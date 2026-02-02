"""Unit tests for the embedding provider."""

import pytest
from unittest.mock import MagicMock, patch


class TestLocalEmbeddingProvider:
    """Tests for LocalEmbeddingProvider."""

    def test_embed_returns_list_of_floats(self):
        """Should return a list of floats for a single text."""
        # Mock the SentenceTransformer to avoid loading the actual model
        with patch("app.core.embeddings.SentenceTransformer") as mock_st:
            import numpy as np

            mock_model = MagicMock()
            mock_model.encode.return_value = np.array([0.1, 0.2, 0.3, 0.4])
            mock_model.get_sentence_embedding_dimension.return_value = 768
            mock_st.return_value = mock_model

            from app.core.embeddings import LocalEmbeddingProvider

            provider = LocalEmbeddingProvider("test-model")
            result = provider.embed("Hello world")

            assert isinstance(result, list)
            assert all(isinstance(x, float) for x in result)
            mock_model.encode.assert_called_once_with(
                "Hello world", normalize_embeddings=True
            )

    def test_embed_batch_returns_list_of_embeddings(self):
        """Should return a list of embeddings for multiple texts."""
        with patch("app.core.embeddings.SentenceTransformer") as mock_st:
            import numpy as np

            mock_model = MagicMock()
            mock_model.encode.return_value = np.array(
                [[0.1, 0.2], [0.3, 0.4], [0.5, 0.6]]
            )
            mock_model.get_sentence_embedding_dimension.return_value = 768
            mock_st.return_value = mock_model

            from app.core.embeddings import LocalEmbeddingProvider

            provider = LocalEmbeddingProvider("test-model")
            texts = ["Text 1", "Text 2", "Text 3"]
            result = provider.embed_batch(texts)

            assert isinstance(result, list)
            assert len(result) == 3
            assert all(isinstance(emb, list) for emb in result)
            mock_model.encode.assert_called_once_with(texts, normalize_embeddings=True)

    def test_dimension_property(self):
        """Should return the correct embedding dimension."""
        with patch("app.core.embeddings.SentenceTransformer") as mock_st:
            mock_model = MagicMock()
            mock_model.get_sentence_embedding_dimension.return_value = 768
            mock_st.return_value = mock_model

            from app.core.embeddings import LocalEmbeddingProvider

            provider = LocalEmbeddingProvider("test-model")

            assert provider.dimension == 768

    def test_lazy_model_loading(self):
        """Should only load the model when first accessed."""
        with patch("app.core.embeddings.SentenceTransformer") as mock_st:
            mock_model = MagicMock()
            mock_st.return_value = mock_model

            from app.core.embeddings import LocalEmbeddingProvider

            provider = LocalEmbeddingProvider("test-model")

            # Model should not be loaded yet
            mock_st.assert_not_called()

            # Access the model
            _ = provider.model

            # Now it should be loaded
            mock_st.assert_called_once_with("test-model")


class TestDetectRememberIntent:
    """Tests for remember intent detection."""

    def test_remember_command(self):
        """Should detect /remember command."""
        from app.agents.nodes import detect_remember_intent

        is_remember, content = detect_remember_intent("/remember I prefer dark mode")
        assert is_remember is True
        assert content == "I prefer dark mode"

    def test_remember_command_case_insensitive(self):
        """Should detect /Remember command (case insensitive)."""
        from app.agents.nodes import detect_remember_intent

        is_remember, content = detect_remember_intent("/REMEMBER my name is John")
        assert is_remember is True
        assert content == "my name is John"

    def test_natural_remember_that(self):
        """Should detect 'remember that' pattern."""
        from app.agents.nodes import detect_remember_intent

        is_remember, content = detect_remember_intent(
            "remember that I work at Acme Corp"
        )
        assert is_remember is True
        assert content == "I work at Acme Corp"

    def test_natural_please_remember(self):
        """Should detect 'please remember that' pattern."""
        from app.agents.nodes import detect_remember_intent

        is_remember, content = detect_remember_intent(
            "please remember that I prefer Python over JavaScript"
        )
        assert is_remember is True
        assert content == "I prefer Python over JavaScript"

    def test_natural_save_to_memory(self):
        """Should detect 'save to memory' pattern."""
        from app.agents.nodes import detect_remember_intent

        is_remember, content = detect_remember_intent(
            "save to memory: I live in San Francisco"
        )
        assert is_remember is True
        assert content == "I live in San Francisco"

    def test_natural_note_that(self):
        """Should detect 'note that' pattern."""
        from app.agents.nodes import detect_remember_intent

        is_remember, content = detect_remember_intent("note that I'm allergic to cats")
        assert is_remember is True
        assert content == "I'm allergic to cats"

    def test_regular_message_not_detected(self):
        """Should not detect regular messages as remember intent."""
        from app.agents.nodes import detect_remember_intent

        is_remember, content = detect_remember_intent("What's the weather today?")
        assert is_remember is False
        assert content is None

    def test_remember_in_middle_not_detected(self):
        """Should not detect 'remember' in the middle of a sentence."""
        from app.agents.nodes import detect_remember_intent

        is_remember, content = detect_remember_intent(
            "I can't remember what I did yesterday"
        )
        assert is_remember is False
        assert content is None


class TestInferMemoryType:
    """Tests for memory type inference."""

    def test_infer_preference_i_prefer(self):
        """Should infer 'preference' for 'I prefer' statements."""
        from app.agents.nodes import infer_memory_type

        assert infer_memory_type("I prefer dark mode") == "preference"

    def test_infer_preference_i_like(self):
        """Should infer 'preference' for 'I like' statements."""
        from app.agents.nodes import infer_memory_type

        assert infer_memory_type("I like concise responses") == "preference"

    def test_infer_preference_i_dont_like(self):
        """Should infer 'preference' for 'I don't like' statements."""
        from app.agents.nodes import infer_memory_type

        assert infer_memory_type("I don't like long explanations") == "preference"

    def test_infer_preference_my_favorite(self):
        """Should infer 'preference' for 'my favorite' statements."""
        from app.agents.nodes import infer_memory_type

        assert infer_memory_type("My favorite color is blue") == "preference"

    def test_infer_knowledge_default(self):
        """Should default to 'knowledge' for factual statements."""
        from app.agents.nodes import infer_memory_type

        assert infer_memory_type("I work at Acme Corp") == "knowledge"
        assert infer_memory_type("My birthday is March 15") == "knowledge"
