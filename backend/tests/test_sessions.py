import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.factories import UserFactory, SessionFactory


@pytest.fixture
async def test_user(db_session: AsyncSession):
    """Create a test user."""
    user = UserFactory()
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


class TestCreateSession:
    """Tests for POST /api/sessions."""

    async def test_create_session_success(
        self,
        client: AsyncClient,
        test_user,
    ):
        """Should create a session successfully."""
        response = await client.post(
            "/api/sessions",
            json={"title": "Test Session"},
            headers={"X-User-Id": test_user.id},
        )

        assert response.status_code == 201
        data = response.json()
        assert data["title"] == "Test Session"
        assert data["source"] == "webapp"
        assert "id" in data
        assert "created_at" in data

    async def test_create_session_without_title(
        self,
        client: AsyncClient,
        test_user,
    ):
        """Should create a session without title."""
        response = await client.post(
            "/api/sessions",
            json={},
            headers={"X-User-Id": test_user.id},
        )

        assert response.status_code == 201
        data = response.json()
        assert data["title"] is None

    async def test_create_session_unauthorized(
        self,
        client: AsyncClient,
    ):
        """Should return 401 without auth header."""
        response = await client.post(
            "/api/sessions",
            json={"title": "Test Session"},
        )

        assert response.status_code == 401


class TestListSessions:
    """Tests for GET /api/sessions."""

    async def test_list_sessions_empty(
        self,
        client: AsyncClient,
        test_user,
    ):
        """Should return empty list when no sessions."""
        response = await client.get(
            "/api/sessions",
            headers={"X-User-Id": test_user.id},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["items"] == []
        assert data["total"] == 0
        assert data["page"] == 1
        assert data["size"] == 20

    async def test_list_sessions_with_data(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user,
    ):
        """Should return sessions for the user."""
        # Create sessions
        session1 = SessionFactory(user_id=test_user.id, title="Session 1")
        session2 = SessionFactory(user_id=test_user.id, title="Session 2")
        db_session.add_all([session1, session2])
        await db_session.commit()

        response = await client.get(
            "/api/sessions",
            headers={"X-User-Id": test_user.id},
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 2
        assert data["total"] == 2

    async def test_list_sessions_pagination(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user,
    ):
        """Should respect pagination parameters."""
        # Create 5 sessions
        sessions = [
            SessionFactory(user_id=test_user.id, title=f"Session {i}")
            for i in range(5)
        ]
        db_session.add_all(sessions)
        await db_session.commit()

        response = await client.get(
            "/api/sessions?page=1&size=2",
            headers={"X-User-Id": test_user.id},
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 2
        assert data["total"] == 5
        assert data["page"] == 1
        assert data["size"] == 2


class TestGetSession:
    """Tests for GET /api/sessions/{id}."""

    async def test_get_session_success(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user,
    ):
        """Should return session with messages."""
        session = SessionFactory(user_id=test_user.id, title="Test Session")
        db_session.add(session)
        await db_session.commit()
        await db_session.refresh(session)

        response = await client.get(
            f"/api/sessions/{session.id}",
            headers={"X-User-Id": test_user.id},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == session.id
        assert data["title"] == "Test Session"
        assert "messages" in data

    async def test_get_session_not_found(
        self,
        client: AsyncClient,
        test_user,
    ):
        """Should return 404 for non-existent session."""
        response = await client.get(
            "/api/sessions/00000000-0000-0000-0000-000000000000",
            headers={"X-User-Id": test_user.id},
        )

        assert response.status_code == 404

    async def test_get_session_forbidden(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user,
    ):
        """Should return 403 for session owned by another user."""
        other_user = UserFactory()
        db_session.add(other_user)
        await db_session.commit()

        session = SessionFactory(user_id=other_user.id)
        db_session.add(session)
        await db_session.commit()
        await db_session.refresh(session)

        response = await client.get(
            f"/api/sessions/{session.id}",
            headers={"X-User-Id": test_user.id},
        )

        assert response.status_code == 403


class TestDeleteSession:
    """Tests for DELETE /api/sessions/{id}."""

    async def test_delete_session_success(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user,
    ):
        """Should delete session successfully."""
        session = SessionFactory(user_id=test_user.id)
        db_session.add(session)
        await db_session.commit()
        await db_session.refresh(session)

        response = await client.delete(
            f"/api/sessions/{session.id}",
            headers={"X-User-Id": test_user.id},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

        # Verify session is deleted
        get_response = await client.get(
            f"/api/sessions/{session.id}",
            headers={"X-User-Id": test_user.id},
        )
        assert get_response.status_code == 404

    async def test_delete_session_not_found(
        self,
        client: AsyncClient,
        test_user,
    ):
        """Should return 404 for non-existent session."""
        response = await client.delete(
            "/api/sessions/00000000-0000-0000-0000-000000000000",
            headers={"X-User-Id": test_user.id},
        )

        assert response.status_code == 404

    async def test_delete_session_forbidden(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user,
    ):
        """Should return 403 for session owned by another user."""
        other_user = UserFactory()
        db_session.add(other_user)
        await db_session.commit()

        session = SessionFactory(user_id=other_user.id)
        db_session.add(session)
        await db_session.commit()
        await db_session.refresh(session)

        response = await client.delete(
            f"/api/sessions/{session.id}",
            headers={"X-User-Id": test_user.id},
        )

        assert response.status_code == 403
