"""Memory repository with semantic search capabilities."""

from datetime import datetime

from sqlalchemy import select, func, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Memory
from app.db.repositories.base import BaseRepository


class MemoryRepository(BaseRepository[Memory]):
    """Repository for Memory model with pgvector semantic search."""

    def __init__(self, db: AsyncSession):
        super().__init__(Memory, db)

    async def create_memory(
        self,
        user_id: str,
        type: str,
        content: str,
        embedding: list[float] | None = None,
        source_session_id: str | None = None,
    ) -> Memory:
        """
        Create a new memory.

        Args:
            user_id: The user ID this memory belongs to.
            type: Memory type ('preference', 'knowledge', 'summary').
            content: The memory content.
            embedding: Optional pre-computed embedding vector.
            source_session_id: Optional session ID this memory was extracted from.

        Returns:
            The created Memory object.
        """
        memory = Memory(
            user_id=user_id,
            type=type,
            content=content,
            embedding=embedding,
            source_session_id=source_session_id,
        )
        return await self.create(memory)

    async def get_user_memories(
        self,
        user_id: str,
        *,
        type: str | None = None,
        skip: int = 0,
        limit: int = 20,
    ) -> list[Memory]:
        """
        Get memories for a specific user, optionally filtered by type.

        Args:
            user_id: The user ID to get memories for.
            type: Optional memory type filter.
            skip: Number of records to skip.
            limit: Maximum number of records to return.

        Returns:
            List of Memory objects.
        """
        filters: dict[str, str] = {"user_id": user_id}
        if type is not None:
            filters["type"] = type

        return await self.get_multi(
            skip=skip,
            limit=limit,
            order_by=Memory.created_at.desc(),
            **filters,
        )

    async def count_user_memories(
        self,
        user_id: str,
        *,
        type: str | None = None,
    ) -> int:
        """Count memories for a specific user."""
        filters: dict[str, str] = {"user_id": user_id}
        if type is not None:
            filters["type"] = type
        return await self.count(**filters)

    async def search_similar(
        self,
        user_id: str,
        query_embedding: list[float],
        *,
        limit: int = 5,
        min_similarity: float | None = None,
    ) -> list[tuple[Memory, float]]:
        """
        Search for semantically similar memories using pgvector.

        Args:
            user_id: The user ID to search memories for.
            query_embedding: The embedding vector to search with.
            limit: Maximum number of results to return.
            min_similarity: Optional minimum cosine similarity threshold.

        Returns:
            List of tuples (Memory, similarity_score) ordered by similarity.
        """
        # Use cosine distance (1 - cosine_similarity)
        # pgvector <=> operator returns cosine distance
        similarity = (1 - Memory.embedding.cosine_distance(query_embedding)).label(
            "similarity"
        )

        query = (
            select(Memory, similarity)
            .where(Memory.user_id == user_id)
            .where(Memory.embedding.is_not(None))
            .order_by(Memory.embedding.cosine_distance(query_embedding))
            .limit(limit)
        )

        if min_similarity is not None:
            # Filter by minimum similarity (convert to max distance)
            max_distance = 1 - min_similarity
            query = query.where(
                Memory.embedding.cosine_distance(query_embedding) <= max_distance
            )

        result = await self.db.execute(query)
        rows = result.all()
        return [(row[0], float(row[1])) for row in rows]

    async def find_duplicate(
        self,
        user_id: str,
        embedding: list[float],
        threshold: float = 0.95,
    ) -> Memory | None:
        """
        Find a memory that is very similar (potential duplicate).

        Args:
            user_id: The user ID to search memories for.
            embedding: The embedding to check for duplicates.
            threshold: Similarity threshold above which a memory is considered duplicate.

        Returns:
            The duplicate Memory if found, None otherwise.
        """
        results = await self.search_similar(
            user_id=user_id,
            query_embedding=embedding,
            limit=1,
            min_similarity=threshold,
        )
        return results[0][0] if results else None

    async def get_last_extraction_time(self, user_id: str) -> datetime | None:
        """
        Get the most recent extraction timestamp for a user.

        This looks at the most recently created memory with a source_session_id
        to determine when extraction last ran.

        Args:
            user_id: The user ID to check.

        Returns:
            The datetime of the last extraction, or None if never extracted.
        """
        result = await self.db.execute(
            select(func.max(Memory.created_at))
            .where(Memory.user_id == user_id)
            .where(Memory.source_session_id.is_not(None))
        )
        return result.scalar_one_or_none()

    async def update_memory(
        self,
        memory: Memory,
        content: str,
        embedding: list[float] | None = None,
    ) -> Memory:
        """
        Update a memory's content and optionally re-embed.

        Args:
            memory: The memory to update.
            content: The new content.
            embedding: Optional new embedding vector.

        Returns:
            The updated Memory object.
        """
        updates: dict[str, str | list[float]] = {"content": content}
        if embedding is not None:
            updates["embedding"] = embedding
        return await self.update(memory, **updates)
