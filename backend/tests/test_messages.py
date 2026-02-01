import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.factories import UserFactory, SessionFactory, MessageFactory


@pytest.fixture
async def test_user(db_session: AsyncSession):
    """Create a test user."""
    user = UserFactory()
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest.fixture
async def test_session(db_session: AsyncSession, test_user):
    """Create a test session."""
    session = SessionFactory(user_id=test_user.id)
    db_session.add(session)
    await db_session.commit()
    await db_session.refresh(session)
    return session


class TestGetMessages:
    """Tests for GET /api/sessions/{id}/messages."""

    async def test_get_messages_empty(
        self,
        client: AsyncClient,
        test_user,
        test_session,
    ):
        """Should return empty list when no messages."""
        response = await client.get(
            f"/api/sessions/{test_session.id}/messages",
            headers={"X-User-Id": test_user.id},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["items"] == []
        assert data["total"] == 0

    async def test_get_messages_with_data(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user,
        test_session,
    ):
        """Should return messages for the session."""
        msg1 = MessageFactory(
            session_id=test_session.id,
            role="user",
            content="Hello",
        )
        msg2 = MessageFactory(
            session_id=test_session.id,
            role="assistant",
            content="Hi there!",
        )
        db_session.add_all([msg1, msg2])
        await db_session.commit()

        response = await client.get(
            f"/api/sessions/{test_session.id}/messages",
            headers={"X-User-Id": test_user.id},
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 2
        assert data["total"] == 2

    async def test_get_messages_session_not_found(
        self,
        client: AsyncClient,
        test_user,
    ):
        """Should return 404 for non-existent session."""
        response = await client.get(
            "/api/sessions/00000000-0000-0000-0000-000000000000/messages",
            headers={"X-User-Id": test_user.id},
        )

        assert response.status_code == 404

    async def test_get_messages_forbidden(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user,
    ):
        """Should return 403 for session owned by another user."""
        other_user = UserFactory()
        db_session.add(other_user)
        await db_session.commit()

        other_session = SessionFactory(user_id=other_user.id)
        db_session.add(other_session)
        await db_session.commit()
        await db_session.refresh(other_session)

        response = await client.get(
            f"/api/sessions/{other_session.id}/messages",
            headers={"X-User-Id": test_user.id},
        )

        assert response.status_code == 403


class TestSendMessage:
    """Tests for POST /api/sessions/{id}/messages."""

    async def test_send_message_session_not_found(
        self,
        client: AsyncClient,
        test_user,
    ):
        """Should return 404 for non-existent session."""
        response = await client.post(
            "/api/sessions/00000000-0000-0000-0000-000000000000/messages",
            json={"content": "Hello"},
            headers={"X-User-Id": test_user.id},
        )

        assert response.status_code == 404

    async def test_send_message_forbidden(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user,
    ):
        """Should return 403 for session owned by another user."""
        other_user = UserFactory()
        db_session.add(other_user)
        await db_session.commit()

        other_session = SessionFactory(user_id=other_user.id)
        db_session.add(other_session)
        await db_session.commit()
        await db_session.refresh(other_session)

        response = await client.post(
            f"/api/sessions/{other_session.id}/messages",
            json={"content": "Hello"},
            headers={"X-User-Id": test_user.id},
        )

        assert response.status_code == 403

    async def test_send_message_unauthorized(
        self,
        client: AsyncClient,
        test_session,
    ):
        """Should return 401 without auth header."""
        response = await client.post(
            f"/api/sessions/{test_session.id}/messages",
            json={"content": "Hello"},
        )

        assert response.status_code == 401
