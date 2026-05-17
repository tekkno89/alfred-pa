"""Tests for the triage away mode API endpoints."""

import pytest
from unittest.mock import AsyncMock, patch

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.dashboard import UserFeatureAccess
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


class TestAwayModeToggle:
    """Tests for away mode toggle endpoint."""

    async def test_toggle_away_mode_on(self, client: AsyncClient, test_user):
        """Test enabling away mode."""
        response = await client.post(
            "/api/triage/away-mode/toggle",
            json={"enabled": True},
            headers=auth_headers(test_user),
        )
        assert response.status_code == 200
        data = response.json()
        assert data["enabled"] is True
        assert data["queued_count"] == 0

    async def test_toggle_away_mode_off(self, client: AsyncClient, test_user):
        """Test disabling away mode."""
        await client.post(
            "/api/triage/away-mode/toggle",
            json={"enabled": True},
            headers=auth_headers(test_user),
        )

        response = await client.post(
            "/api/triage/away-mode/toggle",
            json={"enabled": False},
            headers=auth_headers(test_user),
        )
        assert response.status_code == 200
        data = response.json()
        assert data["enabled"] is False
        assert data["queued_count"] == 0

    async def test_toggle_away_mode_idempotent(
        self, client: AsyncClient, test_user
    ):
        """Test that toggling to the same state is idempotent."""
        response1 = await client.post(
            "/api/triage/away-mode/toggle",
            json={"enabled": True},
            headers=auth_headers(test_user),
        )
        assert response1.status_code == 200

        response2 = await client.post(
            "/api/triage/away-mode/toggle",
            json={"enabled": True},
            headers=auth_headers(test_user),
        )
        assert response2.status_code == 200
        assert response2.json()["queued_count"] == 0

    async def test_toggle_requires_feature_access(
        self, client: AsyncClient, user_no_access
    ):
        """Test that toggle requires triage feature access."""
        response = await client.post(
            "/api/triage/away-mode/toggle",
            json={"enabled": True},
            headers=auth_headers(user_no_access),
        )
        assert response.status_code == 403

    async def test_toggle_missing_enabled_field(self, client: AsyncClient, test_user):
        """Test validation error for missing enabled field."""
        response = await client.post(
            "/api/triage/away-mode/toggle",
            json={},
            headers=auth_headers(test_user),
        )
        assert response.status_code == 422


class TestAwayModeConfigure:
    """Tests for away mode configure endpoint."""

    async def test_configure_push_immediately(
        self, client: AsyncClient, test_user
    ):
        """Test configuring away mode to push immediately."""
        response = await client.post(
            "/api/triage/away-mode/configure",
            json={"notify_now_behavior": "push_immediately"},
            headers=auth_headers(test_user),
        )
        assert response.status_code == 200
        data = response.json()
        assert data["away_mode_notify_now_behavior"] == "push_immediately"

    async def test_configure_queue_for_catchup(
        self, client: AsyncClient, test_user
    ):
        """Test configuring away mode to queue for catchup."""
        response = await client.post(
            "/api/triage/away-mode/configure",
            json={"notify_now_behavior": "queue_for_catchup"},
            headers=auth_headers(test_user),
        )
        assert response.status_code == 200
        data = response.json()
        assert data["away_mode_notify_now_behavior"] == "queue_for_catchup"

    async def test_configure_requires_feature_access(
        self, client: AsyncClient, user_no_access
    ):
        """Test that configure requires triage feature access."""
        response = await client.post(
            "/api/triage/away-mode/configure",
            json={"notify_now_behavior": "push_immediately"},
            headers=auth_headers(user_no_access),
        )
        assert response.status_code == 403

    async def test_configure_invalid_behavior(
        self, client: AsyncClient, test_user
    ):
        """Test validation error for invalid behavior value."""
        response = await client.post(
            "/api/triage/away-mode/configure",
            json={"notify_now_behavior": "invalid"},
            headers=auth_headers(test_user),
        )
        assert response.status_code == 422
