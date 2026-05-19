"""Integration tests for triage message types endpoints."""

import json
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.dashboard import UserFeatureAccess
from app.db.models.triage import ChannelTypeRule, MessageType
from tests.conftest import auth_headers
from tests.factories import UserFactory


@pytest.fixture
async def test_user(db_session: AsyncSession):
    """Create a test user with triage feature access."""
    user = UserFactory()
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    access = UserFeatureAccess(
        user_id=user.id,
        feature_key="card:triage",
        enabled=True,
        granted_by=user.id,
    )
    db_session.add(access)
    await db_session.commit()
    return user


@pytest.fixture
async def user_no_access(db_session: AsyncSession):
    """Create a test user without triage feature access."""
    user = UserFactory()
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest.fixture
async def other_user(db_session: AsyncSession):
    """Create another user with triage access."""
    user = UserFactory()
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    access = UserFeatureAccess(
        user_id=user.id,
        feature_key="card:triage",
        enabled=True,
        granted_by=user.id,
    )
    db_session.add(access)
    await db_session.commit()
    return user


@pytest.fixture
async def message_type(db_session: AsyncSession, test_user):
    """Create a test message type."""
    mt = MessageType(
        user_id=test_user.id,
        type_name="Incidents",
        type_definition="Production incidents and outages",
        source="user",
    )
    db_session.add(mt)
    await db_session.commit()
    await db_session.refresh(mt)
    return mt


@pytest.fixture
async def archived_message_type(db_session: AsyncSession, test_user):
    """Create an archived message type."""
    mt = MessageType(
        user_id=test_user.id,
        type_name="Old Type",
        type_definition="An archived type",
        source="user",
        is_archived=True,
    )
    db_session.add(mt)
    await db_session.commit()
    await db_session.refresh(mt)
    return mt


class TestListMessageTypes:
    """Tests for list_message_types endpoint."""

    async def test_list_message_types_empty(
        self, client: AsyncClient, test_user
    ):
        """Test listing when no message types exist."""
        response = await client.get(
            "/api/triage/message-types", headers=auth_headers(test_user)
        )
        assert response.status_code == 200
        assert response.json() == []

    async def test_list_message_types_excludes_archived(
        self, client: AsyncClient, test_user, message_type, archived_message_type
    ):
        """Test that archived types are excluded by default."""
        response = await client.get(
            "/api/triage/message-types", headers=auth_headers(test_user)
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["type_name"] == "Incidents"

    async def test_list_message_types_includes_archived(
        self, client: AsyncClient, test_user, message_type, archived_message_type
    ):
        """Test that archived types are included when requested."""
        response = await client.get(
            "/api/triage/message-types?include_archived=true",
            headers=auth_headers(test_user),
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2
        names = [mt["type_name"] for mt in data]
        assert "Incidents" in names
        assert "Old Type" in names

    async def test_list_message_types_only_users_own(
        self, client: AsyncClient, db_session: AsyncSession, test_user, other_user
    ):
        """Test that users only see their own message types."""
        mt1 = MessageType(
            user_id=test_user.id,
            type_name="User1 Type",
            type_definition="Definition 1",
            source="user",
        )
        mt2 = MessageType(
            user_id=other_user.id,
            type_name="User2 Type",
            type_definition="Definition 2",
            source="user",
        )
        db_session.add_all([mt1, mt2])
        await db_session.commit()

        response = await client.get(
            "/api/triage/message-types", headers=auth_headers(test_user)
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["type_name"] == "User1 Type"

    async def test_list_message_types_requires_auth(self, client: AsyncClient):
        """Test that endpoint requires authentication."""
        response = await client.get("/api/triage/message-types")
        assert response.status_code == 401


class TestCreateMessageType:
    """Tests for create_message_type endpoint."""

    async def test_create_message_type(self, client: AsyncClient, test_user):
        """Test creating a message type."""
        response = await client.post(
            "/api/triage/message-types",
            json={
                "type_name": "Code Reviews",
                "type_definition": "Pull requests and code review requests",
            },
            headers=auth_headers(test_user),
        )
        assert response.status_code == 201
        data = response.json()
        assert data["type_name"] == "Code Reviews"
        assert data["type_definition"] == "Pull requests and code review requests"
        assert data["source"] == "user"
        assert data["is_archived"] is False
        assert "id" in data
        assert "created_at" in data

    async def test_create_message_type_requires_auth(
        self, client: AsyncClient
    ):
        """Test that endpoint requires authentication."""
        response = await client.post(
            "/api/triage/message-types",
            json={"type_name": "Test", "type_definition": "Test definition"},
        )
        assert response.status_code == 401


class TestUpdateMessageType:
    """Tests for update_message_type endpoint."""

    async def test_update_message_type(
        self, client: AsyncClient, test_user, message_type
    ):
        """Test updating a message type."""
        response = await client.put(
            f"/api/triage/message-types/{message_type.id}",
            json={
                "type_name": "Updated Name",
                "type_definition": "Updated definition",
            },
            headers=auth_headers(test_user),
        )
        assert response.status_code == 200
        data = response.json()
        assert data["type_name"] == "Updated Name"
        assert data["type_definition"] == "Updated definition"

    async def test_update_message_type_partial(
        self, client: AsyncClient, test_user, message_type
    ):
        """Test partial update of a message type."""
        response = await client.put(
            f"/api/triage/message-types/{message_type.id}",
            json={"type_name": "New Name"},
            headers=auth_headers(test_user),
        )
        assert response.status_code == 200
        data = response.json()
        assert data["type_name"] == "New Name"
        assert data["type_definition"] == "Production incidents and outages"

    async def test_update_message_type_not_found(
        self, client: AsyncClient, test_user
    ):
        """Test updating non-existent message type."""
        import uuid

        fake_id = str(uuid.uuid4())
        response = await client.put(
            f"/api/triage/message-types/{fake_id}",
            json={"type_name": "New Name"},
            headers=auth_headers(test_user),
        )
        assert response.status_code == 404

    async def test_update_message_type_other_user(
        self, client: AsyncClient, test_user, other_user, message_type
    ):
        """Test that users cannot update other users' message types."""
        response = await client.put(
            f"/api/triage/message-types/{message_type.id}",
            json={"type_name": "Hacked"},
            headers=auth_headers(other_user),
        )
        assert response.status_code == 404


class TestArchiveMessageType:
    """Tests for archive_message_type endpoint."""

    async def test_archive_message_type(
        self, client: AsyncClient, db_session: AsyncSession, test_user, message_type
    ):
        """Test archiving a message type."""
        response = await client.delete(
            f"/api/triage/message-types/{message_type.id}",
            headers=auth_headers(test_user),
        )
        assert response.status_code == 204

        await db_session.refresh(message_type)
        assert message_type.is_archived is True

    async def test_archive_message_type_not_found(
        self, client: AsyncClient, test_user
    ):
        """Test archiving non-existent message type."""
        import uuid

        fake_id = str(uuid.uuid4())
        response = await client.delete(
            f"/api/triage/message-types/{fake_id}",
            headers=auth_headers(test_user),
        )
        assert response.status_code == 404


class TestCreateChannelTypeRule:
    """Tests for create_channel_type_rule endpoint."""

    async def test_create_channel_type_rule(
        self, client: AsyncClient, test_user, message_type
    ):
        """Test creating a channel type rule."""
        response = await client.post(
            f"/api/triage/channels/C12345/type-rules",
            json={
                "message_type_id": str(message_type.id),
                "action": "notify_now",
            },
            headers=auth_headers(test_user),
        )
        assert response.status_code == 201
        data = response.json()
        assert data["channel_id"] == "C12345"
        assert data["action"] == "notify_now"
        assert data["message_type"]["type_name"] == "Incidents"

    async def test_create_channel_type_rule_invalid_message_type(
        self, client: AsyncClient, test_user, other_user
    ):
        """Test creating rule with non-existent message type."""
        import uuid

        fake_id = str(uuid.uuid4())
        response = await client.post(
            "/api/triage/channels/C12345/type-rules",
            json={
                "message_type_id": fake_id,
                "action": "notify_now",
            },
            headers=auth_headers(test_user),
        )
        assert response.status_code == 404

    async def test_create_channel_type_rule_other_users_type(
        self, client: AsyncClient, db_session: AsyncSession, test_user, other_user
    ):
        """Test creating rule with another user's message type."""
        mt = MessageType(
            user_id=other_user.id,
            type_name="Other Type",
            type_definition="Definition",
            source="user",
        )
        db_session.add(mt)
        await db_session.commit()
        await db_session.refresh(mt)

        response = await client.post(
            "/api/triage/channels/C12345/type-rules",
            json={
                "message_type_id": str(mt.id),
                "action": "notify_now",
            },
            headers=auth_headers(test_user),
        )
        assert response.status_code == 404


class TestListChannelTypeRules:
    """Tests for list_channel_type_rules endpoint."""

    async def test_list_channel_type_rules(
        self, client: AsyncClient, db_session: AsyncSession, test_user, message_type
    ):
        """Test listing channel type rules."""
        rule = ChannelTypeRule(
            user_id=test_user.id,
            channel_id="C12345",
            message_type_id=message_type.id,
            action="notify_now",
        )
        db_session.add(rule)
        await db_session.commit()

        response = await client.get(
            "/api/triage/channels/C12345/type-rules",
            headers=auth_headers(test_user),
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["action"] == "notify_now"
        assert data[0]["message_type"]["type_name"] == "Incidents"

    async def test_list_channel_type_rules_empty(
        self, client: AsyncClient, test_user
    ):
        """Test listing rules when none exist."""
        response = await client.get(
            "/api/triage/channels/C12345/type-rules",
            headers=auth_headers(test_user),
        )
        assert response.status_code == 200
        assert response.json() == []

    async def test_list_channel_type_rules_only_users_own(
        self, client: AsyncClient, db_session: AsyncSession, test_user, other_user, message_type
    ):
        """Test that users only see their own rules."""
        rule1 = ChannelTypeRule(
            user_id=test_user.id,
            channel_id="C12345",
            message_type_id=message_type.id,
            action="notify_now",
        )
        mt2 = MessageType(
            user_id=other_user.id,
            type_name="Other Type",
            type_definition="Definition",
            source="user",
        )
        db_session.add(mt2)
        await db_session.commit()
        await db_session.refresh(mt2)

        rule2 = ChannelTypeRule(
            user_id=other_user.id,
            channel_id="C12345",
            message_type_id=mt2.id,
            action="ignore",
        )
        db_session.add_all([rule1, rule2])
        await db_session.commit()

        response = await client.get(
            "/api/triage/channels/C12345/type-rules",
            headers=auth_headers(test_user),
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["action"] == "notify_now"


class TestDeleteChannelTypeRule:
    """Tests for delete_channel_type_rule endpoint."""

    async def test_delete_channel_type_rule(
        self, client: AsyncClient, db_session: AsyncSession, test_user, message_type
    ):
        """Test deleting a channel type rule."""
        rule = ChannelTypeRule(
            user_id=test_user.id,
            channel_id="C12345",
            message_type_id=message_type.id,
            action="notify_now",
        )
        db_session.add(rule)
        await db_session.commit()
        await db_session.refresh(rule)

        response = await client.delete(
            f"/api/triage/channels/C12345/type-rules/{rule.id}",
            headers=auth_headers(test_user),
        )
        assert response.status_code == 204

    async def test_delete_channel_type_rule_not_found(
        self, client: AsyncClient, test_user
    ):
        """Test deleting non-existent rule."""
        import uuid

        fake_id = str(uuid.uuid4())
        response = await client.delete(
            f"/api/triage/channels/C12345/type-rules/{fake_id}",
            headers=auth_headers(test_user),
        )
        assert response.status_code == 404

    async def test_delete_channel_type_rule_other_user(
        self, client: AsyncClient, db_session: AsyncSession, test_user, other_user, message_type
    ):
        """Test that users cannot delete other users' rules."""
        rule = ChannelTypeRule(
            user_id=test_user.id,
            channel_id="C12345",
            message_type_id=message_type.id,
            action="notify_now",
        )
        db_session.add(rule)
        await db_session.commit()
        await db_session.refresh(rule)

        response = await client.delete(
            f"/api/triage/channels/C12345/type-rules/{rule.id}",
            headers=auth_headers(other_user),
        )
        assert response.status_code == 404


class TestGetSuggestions:
    """Tests for get_message_type_suggestions endpoint."""

    async def test_get_suggestions(
        self, client: AsyncClient, test_user
    ):
        """Get AI-suggested message types based on role."""
        mock_response = AsyncMock()
        mock_response.content = json.dumps([
            {"type_name": "Incidents", "type_definition": "Production issues", "confidence": 0.9},
            {"type_name": "Questions", "type_definition": "Direct questions", "confidence": 0.8},
        ])

        with patch("app.core.llm.get_llm_provider") as mock_get_llm:
            mock_llm = AsyncMock()
            mock_llm.ainvoke.return_value = mock_response
            mock_get_llm.return_value = mock_llm

            response = await client.get(
                "/api/triage/message-types/suggestions",
                params={"role": "Software Engineer"},
                headers=auth_headers(test_user),
            )

        assert response.status_code == 200
        data = response.json()
        assert len(data) >= 2
        assert data[0]["type_name"] == "Incidents"

    async def test_get_suggestions_handles_invalid_json(
        self, client: AsyncClient, test_user
    ):
        """Test that invalid JSON from LLM returns empty list."""
        mock_response = AsyncMock()
        mock_response.content = "not valid json {{{"

        with patch("app.core.llm.get_llm_provider") as mock_get_llm:
            mock_llm = AsyncMock()
            mock_llm.ainvoke.return_value = mock_response
            mock_get_llm.return_value = mock_llm

            response = await client.get(
                "/api/triage/message-types/suggestions",
                params={"role": "Software Engineer"},
                headers=auth_headers(test_user),
            )

        assert response.status_code == 200
        assert response.json() == []


class TestFeatureAccessGate:
    """Tests for feature access enforcement."""

    async def test_list_message_types_blocked_without_access(
        self, client: AsyncClient, user_no_access
    ):
        response = await client.get(
            "/api/triage/message-types",
            headers=auth_headers(user_no_access),
        )
        assert response.status_code == 403

    async def test_create_message_type_blocked_without_access(
        self, client: AsyncClient, user_no_access
    ):
        response = await client.post(
            "/api/triage/message-types",
            json={"type_name": "Test", "type_definition": "Test definition"},
            headers=auth_headers(user_no_access),
        )
        assert response.status_code == 403

    async def test_suggestions_blocked_without_access(
        self, client: AsyncClient, user_no_access
    ):
        response = await client.get(
            "/api/triage/message-types/suggestions",
            params={"role": "Software Engineer"},
            headers=auth_headers(user_no_access),
        )
        assert response.status_code == 403
