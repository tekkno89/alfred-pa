"""Tests for Google Calendar API endpoints."""

from datetime import datetime, UTC
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.api.deps import get_current_user


@pytest.fixture
def mock_user():
    """Create a mock authenticated user."""
    user = MagicMock()
    user.id = "test-user-id"
    user.email = "test@example.com"
    user.role = "user"
    return user


class TestGoogleCalendarOAuthUrl:
    """Tests for GET /google-calendar/oauth/url."""

    @pytest_asyncio.fixture
    async def client(self, mock_user):
        app.dependency_overrides[get_current_user] = lambda: mock_user
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as ac:
            yield ac
        app.dependency_overrides.clear()

    async def test_returns_oauth_url(self, client):
        with patch(
            "app.api.google_calendar.GoogleCalendarService"
        ) as mock_svc_cls:
            mock_svc = MagicMock()
            mock_svc.get_oauth_url.return_value = (
                "https://accounts.google.com/o/oauth2/v2/auth?client_id=test&state=abc"
            )
            mock_svc_cls.return_value = mock_svc

            response = await client.get("/api/google-calendar/oauth/url")

        assert response.status_code == 200
        data = response.json()
        assert "url" in data
        assert "accounts.google.com" in data["url"]

    async def test_returns_error_when_not_configured(self, client):
        with patch(
            "app.api.google_calendar.GoogleCalendarService"
        ) as mock_svc_cls:
            mock_svc = MagicMock()
            mock_svc.get_oauth_url.side_effect = ValueError(
                "Google OAuth is not configured"
            )
            mock_svc_cls.return_value = mock_svc

            response = await client.get("/api/google-calendar/oauth/url")

        assert response.status_code == 400

    async def test_passes_account_label(self, client):
        with patch(
            "app.api.google_calendar.GoogleCalendarService"
        ) as mock_svc_cls:
            mock_svc = MagicMock()
            mock_svc.get_oauth_url.return_value = (
                "https://accounts.google.com/o/oauth2/v2/auth?state=abc"
            )
            mock_svc_cls.return_value = mock_svc

            response = await client.get(
                "/api/google-calendar/oauth/url?account_label=work"
            )

        assert response.status_code == 200
        mock_svc.get_oauth_url.assert_called_once_with("test-user-id", "work")


class TestGoogleCalendarConnections:
    """Tests for GET /google-calendar/connections."""

    @pytest_asyncio.fixture
    async def client(self, mock_user):
        app.dependency_overrides[get_current_user] = lambda: mock_user
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as ac:
            yield ac
        app.dependency_overrides.clear()

    async def test_list_connections_empty(self, client):
        with patch(
            "app.api.google_calendar.OAuthTokenRepository"
        ) as mock_repo_cls:
            mock_repo = AsyncMock()
            mock_repo.get_all_by_user_and_provider.return_value = []
            mock_repo_cls.return_value = mock_repo

            response = await client.get("/api/google-calendar/connections")

        assert response.status_code == 200
        data = response.json()
        assert data["connections"] == []

    async def test_list_connections_with_data(self, client):
        mock_token = MagicMock()
        mock_token.id = "token-1"
        mock_token.provider = "google_calendar"
        mock_token.account_label = "personal"
        mock_token.external_account_id = "user@gmail.com"
        mock_token.token_type = "oauth"
        mock_token.scope = "openid email calendar.readonly"
        mock_token.expires_at = None
        mock_token.created_at = datetime(2026, 1, 1, tzinfo=UTC)

        with patch(
            "app.api.google_calendar.OAuthTokenRepository"
        ) as mock_repo_cls:
            mock_repo = AsyncMock()
            mock_repo.get_all_by_user_and_provider.return_value = [mock_token]
            mock_repo_cls.return_value = mock_repo

            response = await client.get("/api/google-calendar/connections")

        assert response.status_code == 200
        data = response.json()
        assert len(data["connections"]) == 1
        assert data["connections"][0]["external_account_id"] == "user@gmail.com"
        assert data["connections"][0]["provider"] == "google_calendar"


class TestDeleteGoogleCalendarConnection:
    """Tests for DELETE /google-calendar/connections/{id}."""

    @pytest_asyncio.fixture
    async def client(self, mock_user):
        app.dependency_overrides[get_current_user] = lambda: mock_user
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as ac:
            yield ac
        app.dependency_overrides.clear()

    async def test_delete_connection_success(self, client):
        with patch(
            "app.api.google_calendar.GoogleCalendarService"
        ) as mock_svc_cls:
            mock_svc = AsyncMock()
            mock_svc.delete_connection.return_value = True
            mock_svc_cls.return_value = mock_svc

            response = await client.delete(
                "/api/google-calendar/connections/token-1"
            )

        assert response.status_code == 204

    async def test_delete_connection_not_found(self, client):
        with patch(
            "app.api.google_calendar.GoogleCalendarService"
        ) as mock_svc_cls:
            mock_svc = AsyncMock()
            mock_svc.delete_connection.return_value = False
            mock_svc_cls.return_value = mock_svc

            response = await client.delete(
                "/api/google-calendar/connections/nonexistent"
            )

        assert response.status_code == 404


class TestGoogleCalendarOAuthCallback:
    """Tests for GET /google-calendar/oauth/callback."""

    @pytest_asyncio.fixture
    async def client(self):
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as ac:
            yield ac

    async def test_callback_invalid_state(self, client):
        with patch(
            "app.api.google_calendar.consume_oauth_state"
        ) as mock_consume:
            mock_consume.return_value = None

            response = await client.get(
                "/api/google-calendar/oauth/callback?code=test&state=invalid",
                follow_redirects=False,
            )

        assert response.status_code == 400

    async def test_callback_success_redirects(self, client):
        with (
            patch(
                "app.api.google_calendar.consume_oauth_state"
            ) as mock_consume,
            patch(
                "app.api.google_calendar.GoogleCalendarService"
            ) as mock_svc_cls,
            patch("app.api.google_calendar.get_settings") as mock_settings,
        ):
            mock_consume.return_value = {
                "user_id": "user-1",
                "account_label": "personal",
            }

            mock_svc = AsyncMock()
            mock_svc.exchange_code.return_value = {
                "access_token": "ya29.test",
                "refresh_token": "1//refresh",
            }
            mock_svc.store_oauth_token.return_value = MagicMock()
            mock_svc_cls.return_value = mock_svc

            settings = MagicMock()
            settings.frontend_url = "http://localhost:3000"
            mock_settings.return_value = settings

            response = await client.get(
                "/api/google-calendar/oauth/callback?code=authcode&state=valid-state",
                follow_redirects=False,
            )

        assert response.status_code == 307
        assert "google_calendar_oauth=success" in response.headers["location"]

    async def test_callback_exchange_error_redirects(self, client):
        with (
            patch(
                "app.api.google_calendar.consume_oauth_state"
            ) as mock_consume,
            patch(
                "app.api.google_calendar.GoogleCalendarService"
            ) as mock_svc_cls,
            patch("app.api.google_calendar.get_settings") as mock_settings,
        ):
            mock_consume.return_value = {
                "user_id": "user-1",
                "account_label": "default",
            }

            mock_svc = AsyncMock()
            mock_svc.exchange_code.side_effect = ValueError("invalid_grant")
            mock_svc_cls.return_value = mock_svc

            settings = MagicMock()
            settings.frontend_url = "http://localhost:3000"
            mock_settings.return_value = settings

            response = await client.get(
                "/api/google-calendar/oauth/callback?code=bad&state=valid",
                follow_redirects=False,
            )

        assert response.status_code == 307
        assert "google_calendar_oauth=error" in response.headers["location"]


class TestCalendarWebhook:
    """Tests for POST /calendar/webhook."""

    @pytest_asyncio.fixture
    async def client(self):
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as ac:
            yield ac

    async def test_webhook_calls_incremental_sync(self, client):
        """Verify webhook triggers handle_push_notification (incremental sync)."""
        with (
            patch(
                "app.api.calendar.GoogleCalendarService"
            ) as mock_svc_cls,
            patch(
                "app.api.calendar.GoogleCalendarService.verify_channel_token",
                return_value=True,
            ),
        ):
            mock_svc = AsyncMock()
            mock_svc.handle_push_notification = AsyncMock()
            mock_svc_cls.return_value = mock_svc

            response = await client.post(
                "/api/calendar/webhook",
                headers={
                    "X-Goog-Channel-ID": "chan-123",
                    "X-Goog-Resource-ID": "res-456",
                    "X-Goog-Resource-State": "exists",
                    "X-Goog-Channel-Token": "valid-token",
                },
            )

        assert response.status_code == 200
        mock_svc.handle_push_notification.assert_called_once_with(
            "chan-123", "res-456"
        )
