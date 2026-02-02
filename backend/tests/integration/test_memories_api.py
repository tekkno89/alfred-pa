"""Integration tests for the memories API endpoints."""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from unittest.mock import patch, MagicMock

from tests.conftest import auth_headers
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
def mock_embedding_provider():
    """Mock the embedding provider to avoid loading the model."""
    with patch("app.api.memories.get_embedding_provider") as mock:
        mock_provider = MagicMock()
        mock_provider.embed.return_value = [0.1] * 768
        mock.return_value = mock_provider
        yield mock_provider


class TestListMemories:
    """Tests for GET /api/memories."""

    async def test_list_memories_empty(
        self,
        client: AsyncClient,
        test_user,
    ):
        """Should return empty list when no memories."""
        response = await client.get(
            "/api/memories",
            headers=auth_headers(test_user),
        )

        assert response.status_code == 200
        data = response.json()
        assert data["items"] == []
        assert data["total"] == 0
        assert data["page"] == 1
        assert data["size"] == 20

    async def test_list_memories_with_data(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user,
    ):
        """Should return user's memories."""
        mem1 = MemoryFactory(user_id=test_user.id, content="Memory 1")
        mem2 = MemoryFactory(user_id=test_user.id, content="Memory 2")
        db_session.add_all([mem1, mem2])
        await db_session.commit()

        response = await client.get(
            "/api/memories",
            headers=auth_headers(test_user),
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 2
        assert data["total"] == 2

    async def test_list_memories_filter_by_type(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user,
    ):
        """Should filter memories by type."""
        mem1 = MemoryFactory(user_id=test_user.id, type="preference")
        mem2 = MemoryFactory(user_id=test_user.id, type="knowledge")
        db_session.add_all([mem1, mem2])
        await db_session.commit()

        response = await client.get(
            "/api/memories?type=preference",
            headers=auth_headers(test_user),
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 1
        assert data["items"][0]["type"] == "preference"

    async def test_list_memories_pagination(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user,
    ):
        """Should paginate memories."""
        for i in range(5):
            db_session.add(MemoryFactory(user_id=test_user.id))
        await db_session.commit()

        response = await client.get(
            "/api/memories?page=1&size=2",
            headers=auth_headers(test_user),
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 2
        assert data["total"] == 5
        assert data["page"] == 1
        assert data["size"] == 2

    async def test_list_memories_unauthorized(
        self,
        client: AsyncClient,
    ):
        """Should return 401 without auth."""
        response = await client.get("/api/memories")
        assert response.status_code == 401


class TestGetMemory:
    """Tests for GET /api/memories/{id}."""

    async def test_get_memory_success(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user,
    ):
        """Should return a specific memory."""
        mem = MemoryFactory(
            user_id=test_user.id,
            type="preference",
            content="I prefer dark mode",
        )
        db_session.add(mem)
        await db_session.commit()
        await db_session.refresh(mem)

        response = await client.get(
            f"/api/memories/{mem.id}",
            headers=auth_headers(test_user),
        )

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == mem.id
        assert data["type"] == "preference"
        assert data["content"] == "I prefer dark mode"

    async def test_get_memory_not_found(
        self,
        client: AsyncClient,
        test_user,
    ):
        """Should return 404 for non-existent memory."""
        response = await client.get(
            "/api/memories/00000000-0000-0000-0000-000000000000",
            headers=auth_headers(test_user),
        )

        assert response.status_code == 404

    async def test_get_memory_forbidden(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user,
    ):
        """Should return 403 for memory owned by another user."""
        other_user = UserFactory()
        db_session.add(other_user)
        await db_session.commit()

        mem = MemoryFactory(user_id=other_user.id)
        db_session.add(mem)
        await db_session.commit()
        await db_session.refresh(mem)

        response = await client.get(
            f"/api/memories/{mem.id}",
            headers=auth_headers(test_user),
        )

        assert response.status_code == 403


class TestCreateMemory:
    """Tests for POST /api/memories."""

    async def test_create_memory_success(
        self,
        client: AsyncClient,
        test_user,
        mock_embedding_provider,
    ):
        """Should create a memory."""
        response = await client.post(
            "/api/memories",
            json={
                "type": "preference",
                "content": "I prefer dark mode",
            },
            headers=auth_headers(test_user),
        )

        assert response.status_code == 201
        data = response.json()
        assert data["type"] == "preference"
        assert data["content"] == "I prefer dark mode"
        assert "id" in data
        assert "created_at" in data

        # Verify embedding was generated
        mock_embedding_provider.embed.assert_called_once_with("I prefer dark mode")

    async def test_create_memory_invalid_type(
        self,
        client: AsyncClient,
        test_user,
    ):
        """Should reject invalid memory type."""
        response = await client.post(
            "/api/memories",
            json={
                "type": "invalid_type",
                "content": "Some content",
            },
            headers=auth_headers(test_user),
        )

        assert response.status_code == 422

    async def test_create_memory_unauthorized(
        self,
        client: AsyncClient,
    ):
        """Should return 401 without auth."""
        response = await client.post(
            "/api/memories",
            json={
                "type": "preference",
                "content": "Some content",
            },
        )

        assert response.status_code == 401


class TestUpdateMemory:
    """Tests for PUT /api/memories/{id}."""

    async def test_update_memory_success(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user,
        mock_embedding_provider,
    ):
        """Should update a memory."""
        mem = MemoryFactory(
            user_id=test_user.id,
            content="Old content",
        )
        db_session.add(mem)
        await db_session.commit()
        await db_session.refresh(mem)

        response = await client.put(
            f"/api/memories/{mem.id}",
            json={"content": "New content"},
            headers=auth_headers(test_user),
        )

        assert response.status_code == 200
        data = response.json()
        assert data["content"] == "New content"

        # Verify embedding was regenerated
        mock_embedding_provider.embed.assert_called_once_with("New content")

    async def test_update_memory_not_found(
        self,
        client: AsyncClient,
        test_user,
    ):
        """Should return 404 for non-existent memory."""
        response = await client.put(
            "/api/memories/00000000-0000-0000-0000-000000000000",
            json={"content": "New content"},
            headers=auth_headers(test_user),
        )

        assert response.status_code == 404

    async def test_update_memory_forbidden(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user,
    ):
        """Should return 403 for memory owned by another user."""
        other_user = UserFactory()
        db_session.add(other_user)
        await db_session.commit()

        mem = MemoryFactory(user_id=other_user.id)
        db_session.add(mem)
        await db_session.commit()
        await db_session.refresh(mem)

        response = await client.put(
            f"/api/memories/{mem.id}",
            json={"content": "New content"},
            headers=auth_headers(test_user),
        )

        assert response.status_code == 403


class TestDeleteMemory:
    """Tests for DELETE /api/memories/{id}."""

    async def test_delete_memory_success(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user,
    ):
        """Should delete a memory."""
        mem = MemoryFactory(user_id=test_user.id)
        db_session.add(mem)
        await db_session.commit()
        await db_session.refresh(mem)

        response = await client.delete(
            f"/api/memories/{mem.id}",
            headers=auth_headers(test_user),
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

        # Verify it's deleted
        get_response = await client.get(
            f"/api/memories/{mem.id}",
            headers=auth_headers(test_user),
        )
        assert get_response.status_code == 404

    async def test_delete_memory_not_found(
        self,
        client: AsyncClient,
        test_user,
    ):
        """Should return 404 for non-existent memory."""
        response = await client.delete(
            "/api/memories/00000000-0000-0000-0000-000000000000",
            headers=auth_headers(test_user),
        )

        assert response.status_code == 404

    async def test_delete_memory_forbidden(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user,
    ):
        """Should return 403 for memory owned by another user."""
        other_user = UserFactory()
        db_session.add(other_user)
        await db_session.commit()

        mem = MemoryFactory(user_id=other_user.id)
        db_session.add(mem)
        await db_session.commit()
        await db_session.refresh(mem)

        response = await client.delete(
            f"/api/memories/{mem.id}",
            headers=auth_headers(test_user),
        )

        assert response.status_code == 403
