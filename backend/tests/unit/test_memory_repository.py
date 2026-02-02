"""Unit tests for the memory repository."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.repositories import MemoryRepository
from tests.factories import MemoryFactory, UserFactory


@pytest.fixture
async def test_user(db_session: AsyncSession):
    """Create a test user."""
    user = UserFactory()
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest.fixture
async def memory_repo(db_session: AsyncSession):
    """Create a memory repository."""
    return MemoryRepository(db_session)


class TestCreateMemory:
    """Tests for creating memories."""

    async def test_create_memory_basic(
        self,
        db_session: AsyncSession,
        memory_repo: MemoryRepository,
        test_user,
    ):
        """Should create a memory with basic fields."""
        memory = await memory_repo.create_memory(
            user_id=test_user.id,
            type="preference",
            content="I prefer dark mode",
        )
        await db_session.commit()

        assert memory.id is not None
        assert memory.user_id == test_user.id
        assert memory.type == "preference"
        assert memory.content == "I prefer dark mode"
        assert memory.embedding is None
        assert memory.source_session_id is None

    async def test_create_memory_with_embedding(
        self,
        db_session: AsyncSession,
        memory_repo: MemoryRepository,
        test_user,
    ):
        """Should create a memory with embedding."""
        embedding = [0.1] * 768  # Mock 768-dim embedding

        memory = await memory_repo.create_memory(
            user_id=test_user.id,
            type="knowledge",
            content="I work at Acme Corp",
            embedding=embedding,
        )
        await db_session.commit()

        assert memory.embedding is not None
        assert len(memory.embedding) == 768


class TestGetUserMemories:
    """Tests for retrieving user memories."""

    async def test_get_user_memories_empty(
        self,
        memory_repo: MemoryRepository,
        test_user,
    ):
        """Should return empty list when user has no memories."""
        memories = await memory_repo.get_user_memories(user_id=test_user.id)
        assert memories == []

    async def test_get_user_memories(
        self,
        db_session: AsyncSession,
        memory_repo: MemoryRepository,
        test_user,
    ):
        """Should return user's memories."""
        # Create some memories
        mem1 = MemoryFactory(user_id=test_user.id, type="preference")
        mem2 = MemoryFactory(user_id=test_user.id, type="knowledge")
        db_session.add_all([mem1, mem2])
        await db_session.commit()

        memories = await memory_repo.get_user_memories(user_id=test_user.id)
        assert len(memories) == 2

    async def test_get_user_memories_filtered_by_type(
        self,
        db_session: AsyncSession,
        memory_repo: MemoryRepository,
        test_user,
    ):
        """Should filter memories by type."""
        mem1 = MemoryFactory(user_id=test_user.id, type="preference")
        mem2 = MemoryFactory(user_id=test_user.id, type="knowledge")
        mem3 = MemoryFactory(user_id=test_user.id, type="preference")
        db_session.add_all([mem1, mem2, mem3])
        await db_session.commit()

        preferences = await memory_repo.get_user_memories(
            user_id=test_user.id, type="preference"
        )
        assert len(preferences) == 2

        knowledge = await memory_repo.get_user_memories(
            user_id=test_user.id, type="knowledge"
        )
        assert len(knowledge) == 1

    async def test_get_user_memories_pagination(
        self,
        db_session: AsyncSession,
        memory_repo: MemoryRepository,
        test_user,
    ):
        """Should paginate memories."""
        for i in range(5):
            db_session.add(MemoryFactory(user_id=test_user.id))
        await db_session.commit()

        page1 = await memory_repo.get_user_memories(
            user_id=test_user.id, skip=0, limit=2
        )
        assert len(page1) == 2

        page2 = await memory_repo.get_user_memories(
            user_id=test_user.id, skip=2, limit=2
        )
        assert len(page2) == 2


class TestCountUserMemories:
    """Tests for counting user memories."""

    async def test_count_user_memories(
        self,
        db_session: AsyncSession,
        memory_repo: MemoryRepository,
        test_user,
    ):
        """Should count user's memories."""
        for i in range(3):
            db_session.add(MemoryFactory(user_id=test_user.id))
        await db_session.commit()

        count = await memory_repo.count_user_memories(user_id=test_user.id)
        assert count == 3

    async def test_count_user_memories_by_type(
        self,
        db_session: AsyncSession,
        memory_repo: MemoryRepository,
        test_user,
    ):
        """Should count memories filtered by type."""
        db_session.add(MemoryFactory(user_id=test_user.id, type="preference"))
        db_session.add(MemoryFactory(user_id=test_user.id, type="preference"))
        db_session.add(MemoryFactory(user_id=test_user.id, type="knowledge"))
        await db_session.commit()

        pref_count = await memory_repo.count_user_memories(
            user_id=test_user.id, type="preference"
        )
        assert pref_count == 2


class TestSearchSimilar:
    """Tests for semantic similarity search."""

    async def test_search_similar_no_embeddings(
        self,
        db_session: AsyncSession,
        memory_repo: MemoryRepository,
        test_user,
    ):
        """Should return empty when no memories have embeddings."""
        mem = MemoryFactory(user_id=test_user.id, embedding=None)
        db_session.add(mem)
        await db_session.commit()

        query_embedding = [0.1] * 768
        results = await memory_repo.search_similar(
            user_id=test_user.id,
            query_embedding=query_embedding,
        )
        assert results == []

    async def test_search_similar_with_embeddings(
        self,
        db_session: AsyncSession,
        memory_repo: MemoryRepository,
        test_user,
    ):
        """Should find similar memories based on embedding."""
        # Create memories with embeddings
        embedding1 = [1.0] + [0.0] * 767  # Point in one direction
        embedding2 = [0.0, 1.0] + [0.0] * 766  # Point in another direction

        mem1 = MemoryFactory(
            user_id=test_user.id,
            content="Memory 1",
            embedding=embedding1,
        )
        mem2 = MemoryFactory(
            user_id=test_user.id,
            content="Memory 2",
            embedding=embedding2,
        )
        db_session.add_all([mem1, mem2])
        await db_session.commit()

        # Search with embedding similar to mem1
        query_embedding = [0.9] + [0.1] * 767
        results = await memory_repo.search_similar(
            user_id=test_user.id,
            query_embedding=query_embedding,
            limit=5,
        )

        assert len(results) == 2
        # First result should be more similar (mem1)
        first_memory, first_score = results[0]
        assert first_memory.content == "Memory 1"


class TestUpdateMemory:
    """Tests for updating memories."""

    async def test_update_memory_content(
        self,
        db_session: AsyncSession,
        memory_repo: MemoryRepository,
        test_user,
    ):
        """Should update memory content."""
        mem = MemoryFactory(user_id=test_user.id, content="Old content")
        db_session.add(mem)
        await db_session.commit()
        await db_session.refresh(mem)

        updated = await memory_repo.update_memory(
            memory=mem,
            content="New content",
        )
        await db_session.commit()

        assert updated.content == "New content"

    async def test_update_memory_with_embedding(
        self,
        db_session: AsyncSession,
        memory_repo: MemoryRepository,
        test_user,
    ):
        """Should update memory content and embedding."""
        mem = MemoryFactory(user_id=test_user.id, content="Old content")
        db_session.add(mem)
        await db_session.commit()
        await db_session.refresh(mem)

        new_embedding = [0.5] * 768
        updated = await memory_repo.update_memory(
            memory=mem,
            content="New content",
            embedding=new_embedding,
        )
        await db_session.commit()

        assert updated.content == "New content"
        assert updated.embedding is not None


class TestDeleteMemory:
    """Tests for deleting memories."""

    async def test_delete_memory(
        self,
        db_session: AsyncSession,
        memory_repo: MemoryRepository,
        test_user,
    ):
        """Should delete a memory."""
        mem = MemoryFactory(user_id=test_user.id)
        db_session.add(mem)
        await db_session.commit()
        await db_session.refresh(mem)
        mem_id = mem.id

        await memory_repo.delete(mem)
        await db_session.commit()

        # Verify it's deleted
        deleted = await memory_repo.get(mem_id)
        assert deleted is None
