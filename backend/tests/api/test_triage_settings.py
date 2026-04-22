"""Integration tests for the triage API endpoints."""

import pytest
from unittest.mock import AsyncMock, patch

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.dashboard import UserFeatureAccess
from app.db.models.triage import MonitoredChannel, ChannelSourceExclusion
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
async def sample_channel(db_session: AsyncSession, test_user):
    """Create a sample monitored channel."""
    channel = MonitoredChannel(
        user_id=test_user.id,
        slack_channel_id="C12345",
        channel_name="general",
        channel_type="public",
        priority="medium",
    )
    db_session.add(channel)
    await db_session.commit()
    await db_session.refresh(channel)
    return channel


# --- Settings ---


class TestTriageSettings:
    async def test_get_settings_creates_defaults(self, client: AsyncClient, test_user):
        response = await client.get(
            "/api/triage/settings",
            headers=auth_headers(test_user),
        )
        assert response.status_code == 200
        data = response.json()
        assert data["is_always_on"] is False
        assert data["sensitivity"] == "medium"
        assert data["debug_mode"] is False
        assert data["classification_retention_days"] == 30

    async def test_update_settings(self, client: AsyncClient, test_user):
        response = await client.patch(
            "/api/triage/settings",
            json={"sensitivity": "high", "is_always_on": True},
            headers=auth_headers(test_user),
        )
        assert response.status_code == 200
        data = response.json()
        assert data["sensitivity"] == "high"
        assert data["is_always_on"] is True

    async def test_save_and_retrieve_custom_classification_rules(
        self, client: AsyncClient, test_user
    ):
        # Save custom rules
        response = await client.patch(
            "/api/triage/settings",
            json={
                "custom_classification_rules": "Requests to borrow items are never urgent"
            },
            headers=auth_headers(test_user),
        )
        assert response.status_code == 200
        data = response.json()
        assert (
            data["custom_classification_rules"]
            == "Requests to borrow items are never urgent"
        )

        # Retrieve and verify
        response = await client.get(
            "/api/triage/settings",
            headers=auth_headers(test_user),
        )
        assert response.status_code == 200
        assert (
            response.json()["custom_classification_rules"]
            == "Requests to borrow items are never urgent"
        )

    async def test_custom_classification_rules_max_length(
        self, client: AsyncClient, test_user
    ):
        long_rules = "x" * 2001
        response = await client.patch(
            "/api/triage/settings",
            json={"custom_classification_rules": long_rules},
            headers=auth_headers(test_user),
        )
        assert response.status_code == 422

    async def test_custom_classification_rules_clear(
        self, client: AsyncClient, test_user
    ):
        # Set rules
        await client.patch(
            "/api/triage/settings",
            json={"custom_classification_rules": "some rule"},
            headers=auth_headers(test_user),
        )
        # Clear rules
        response = await client.patch(
            "/api/triage/settings",
            json={"custom_classification_rules": None},
            headers=auth_headers(test_user),
        )
        assert response.status_code == 200
        assert response.json()["custom_classification_rules"] is None

    async def test_always_on_min_priority_default(self, client: AsyncClient, test_user):
        response = await client.get(
            "/api/triage/settings",
            headers=auth_headers(test_user),
        )
        assert response.status_code == 200
        assert response.json()["always_on_min_priority"] == "p3"

    async def test_update_always_on_min_priority(self, client: AsyncClient, test_user):
        response = await client.patch(
            "/api/triage/settings",
            json={"always_on_min_priority": "p1"},
            headers=auth_headers(test_user),
        )
        assert response.status_code == 200
        assert response.json()["always_on_min_priority"] == "p1"

    async def test_always_on_min_priority_validation(
        self, client: AsyncClient, test_user
    ):
        response = await client.patch(
            "/api/triage/settings",
            json={"always_on_min_priority": "invalid"},
            headers=auth_headers(test_user),
        )
        assert response.status_code == 422

    async def test_settings_requires_feature_access(
        self, client: AsyncClient, user_no_access
    ):
        response = await client.get(
            "/api/triage/settings",
            headers=auth_headers(user_no_access),
        )
        assert response.status_code == 403


# --- Monitored Channels ---


class TestMonitoredChannels:
    @patch("app.api.triage.TriageCacheService")
    async def test_add_channel(self, mock_cache_cls, client: AsyncClient, test_user):
        mock_cache = AsyncMock()
        mock_cache_cls.return_value = mock_cache

        response = await client.post(
            "/api/triage/channels",
            json={
                "slack_channel_id": "C99999",
                "channel_name": "engineering",
                "channel_type": "public",
                "priority": "high",
            },
            headers=auth_headers(test_user),
        )
        assert response.status_code == 201
        data = response.json()
        assert data["slack_channel_id"] == "C99999"
        assert data["channel_name"] == "engineering"
        assert data["priority"] == "high"
        mock_cache.add_channel.assert_called_once_with("C99999")

    @patch("app.api.triage.TriageCacheService")
    async def test_add_duplicate_channel(
        self, mock_cache_cls, client: AsyncClient, test_user, sample_channel
    ):
        mock_cache_cls.return_value = AsyncMock()

        response = await client.post(
            "/api/triage/channels",
            json={
                "slack_channel_id": "C12345",
                "channel_name": "general",
            },
            headers=auth_headers(test_user),
        )
        assert response.status_code == 400

    async def test_list_channels(self, client: AsyncClient, test_user, sample_channel):
        response = await client.get(
            "/api/triage/channels",
            headers=auth_headers(test_user),
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["channels"]) == 1
        assert data["channels"][0]["channel_name"] == "general"

    async def test_update_channel(self, client: AsyncClient, test_user, sample_channel):
        response = await client.patch(
            f"/api/triage/channels/{sample_channel.id}",
            json={"priority": "critical"},
            headers=auth_headers(test_user),
        )
        assert response.status_code == 200
        assert response.json()["priority"] == "critical"

    @patch("app.api.triage.TriageCacheService")
    async def test_delete_channel(
        self, mock_cache_cls, client: AsyncClient, test_user, sample_channel
    ):
        mock_cache = AsyncMock()
        mock_cache_cls.return_value = mock_cache

        response = await client.delete(
            f"/api/triage/channels/{sample_channel.id}",
            headers=auth_headers(test_user),
        )
        assert response.status_code == 204

    async def test_channel_not_found(self, client: AsyncClient, test_user):
        from uuid import uuid4

        fake_id = str(uuid4())
        response = await client.patch(
            f"/api/triage/channels/{fake_id}",
            json={"priority": "high"},
            headers=auth_headers(test_user),
        )
        assert response.status_code == 404


# --- Source Exclusions ---


class TestSourceExclusions:
    async def test_add_exclusion(self, client: AsyncClient, test_user, sample_channel):
        response = await client.post(
            f"/api/triage/channels/{sample_channel.id}/exclusions",
            json={
                "slack_entity_id": "B12345",
                "entity_type": "bot",
                "action": "exclude",
                "display_name": "CI Bot",
            },
            headers=auth_headers(test_user),
        )
        assert response.status_code == 201
        data = response.json()
        assert data["slack_entity_id"] == "B12345"
        assert data["action"] == "exclude"
        assert data["display_name"] == "CI Bot"

    async def test_list_exclusions(
        self, client: AsyncClient, test_user, sample_channel, db_session
    ):
        excl = ChannelSourceExclusion(
            monitored_channel_id=sample_channel.id,
            user_id=test_user.id,
            slack_entity_id="B99999",
            entity_type="bot",
            action="exclude",
        )
        db_session.add(excl)
        await db_session.commit()

        response = await client.get(
            f"/api/triage/channels/{sample_channel.id}/exclusions",
            headers=auth_headers(test_user),
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1

    async def test_delete_exclusion(
        self, client: AsyncClient, test_user, sample_channel, db_session
    ):
        excl = ChannelSourceExclusion(
            monitored_channel_id=sample_channel.id,
            user_id=test_user.id,
            slack_entity_id="B77777",
            entity_type="bot",
            action="exclude",
        )
        db_session.add(excl)
        await db_session.commit()
        await db_session.refresh(excl)

        response = await client.delete(
            f"/api/triage/channels/{sample_channel.id}/exclusions/{excl.id}",
            headers=auth_headers(test_user),
        )
        assert response.status_code == 204


# --- Feature Access Gate ---


class TestFeatureAccessGate:
    """Verify all triage endpoints require card:triage access."""

    async def test_channels_blocked(self, client: AsyncClient, user_no_access):
        response = await client.get(
            "/api/triage/channels",
            headers=auth_headers(user_no_access),
        )
        assert response.status_code == 403

    async def test_classifications_blocked(self, client: AsyncClient, user_no_access):
        response = await client.get(
            "/api/triage/classifications",
            headers=auth_headers(user_no_access),
        )
        assert response.status_code == 403

    async def test_analytics_blocked(self, client: AsyncClient, user_no_access):
        response = await client.get(
            "/api/triage/analytics/session-stats",
            headers=auth_headers(user_no_access),
        )
        assert response.status_code == 403
