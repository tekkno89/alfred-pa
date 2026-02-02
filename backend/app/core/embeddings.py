"""Local embedding provider using sentence-transformers."""

from functools import lru_cache

from sentence_transformers import SentenceTransformer

from app.core.config import get_settings


class LocalEmbeddingProvider:
    """Local embedding provider using sentence-transformers models."""

    def __init__(self, model_name: str | None = None):
        """
        Initialize the embedding provider.

        Args:
            model_name: The sentence-transformers model to use.
                       Defaults to bge-base-en-v1.5 from settings.
        """
        settings = get_settings()
        self._model_name = model_name or settings.embedding_model
        self._model: SentenceTransformer | None = None

    @property
    def model(self) -> SentenceTransformer:
        """Lazy load the model on first use."""
        if self._model is None:
            self._model = SentenceTransformer(self._model_name)
        return self._model

    @property
    def dimension(self) -> int:
        """Get the embedding dimension for this model."""
        return self.model.get_sentence_embedding_dimension()  # type: ignore

    def embed(self, text: str) -> list[float]:
        """
        Generate an embedding for a single text.

        Args:
            text: The text to embed.

        Returns:
            A list of floats representing the embedding.
        """
        embedding = self.model.encode(text, normalize_embeddings=True)
        return embedding.tolist()

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """
        Generate embeddings for multiple texts.

        Args:
            texts: List of texts to embed.

        Returns:
            List of embeddings, one per input text.
        """
        embeddings = self.model.encode(texts, normalize_embeddings=True)
        return embeddings.tolist()


@lru_cache
def get_embedding_provider() -> LocalEmbeddingProvider:
    """Get cached embedding provider instance."""
    return LocalEmbeddingProvider()
