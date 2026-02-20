"""Local embedding provider using fastembed."""

from functools import lru_cache

from fastembed import TextEmbedding

from app.core.config import get_settings


class LocalEmbeddingProvider:
    """Local embedding provider using fastembed (ONNX)."""

    def __init__(self, model_name: str | None = None):
        """
        Initialize the embedding provider.

        Args:
            model_name: The embedding model to use.
                       Defaults to bge-base-en-v1.5 from settings.
        """
        settings = get_settings()
        self._model_name = model_name or settings.embedding_model
        self._model: TextEmbedding | None = None

    @property
    def model(self) -> TextEmbedding:
        """Lazy load the model on first use."""
        if self._model is None:
            self._model = TextEmbedding(model_name=self._model_name)
        return self._model

    @property
    def dimension(self) -> int:
        """Get the embedding dimension for this model."""
        # Embed a dummy string to determine dimension
        sample = list(self.model.embed(["test"]))[0]
        return len(sample)

    def embed(self, text: str) -> list[float]:
        """
        Generate an embedding for a single text.

        Args:
            text: The text to embed.

        Returns:
            A list of floats representing the embedding.
        """
        embeddings = list(self.model.embed([text]))
        return embeddings[0].tolist()

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """
        Generate embeddings for multiple texts.

        Args:
            texts: List of texts to embed.

        Returns:
            List of embeddings, one per input text.
        """
        embeddings = list(self.model.embed(texts))
        return [e.tolist() for e in embeddings]


@lru_cache
def get_embedding_provider() -> LocalEmbeddingProvider:
    """Get cached embedding provider instance."""
    return LocalEmbeddingProvider()
