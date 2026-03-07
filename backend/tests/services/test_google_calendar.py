"""Tests for GoogleCalendarService."""

from datetime import datetime, UTC
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.google_calendar import GoogleCalendarService, PROVIDER


@pytest.fixture
def mock_db() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def gcal_service(mock_db) -> GoogleCalendarService:
    """Create a GoogleCalendarService with mocked dependencies."""
    svc = GoogleCalendarService.__new__(GoogleCalendarService)
    svc.db = mock_db
    svc.token_repo = AsyncMock()
    svc.token_encryption = AsyncMock()
    return svc


class TestGetOAuthUrl:
    """Tests for get_oauth_url."""

    @patch("app.services.google_calendar.get_settings")
    def test_generates_url_with_state(self, mock_settings, gcal_service) -> None:
        settings = MagicMock()
        settings.google_client_id = "test-client-id"
        settings.google_calendar_oauth_redirect_uri = (
            "http://localhost:8000/api/google-calendar/oauth/callback"
        )
        mock_settings.return_value = settings

        url = gcal_service.get_oauth_url("user-1", "personal")

        assert "client_id=test-client-id" in url
        assert "accounts.google.com" in url
        assert "state=" in url
        assert "access_type=offline" in url
        assert "prompt=consent" in url
        assert "auth%2Fcalendar" in url

    @patch("app.services.google_calendar.get_settings")
    def test_raises_if_not_configured(self, mock_settings, gcal_service) -> None:
        settings = MagicMock()
        settings.google_client_id = ""
        mock_settings.return_value = settings

        with pytest.raises(ValueError, match="Google OAuth is not configured"):
            gcal_service.get_oauth_url("user-1")


class TestExchangeCode:
    """Tests for exchange_code."""

    @pytest.mark.asyncio
    @patch("app.services.google_calendar.get_settings")
    async def test_exchanges_code_successfully(
        self, mock_settings, gcal_service
    ) -> None:
        settings = MagicMock()
        settings.google_client_id = "client-id"
        settings.google_client_secret = "client-secret"
        settings.google_calendar_oauth_redirect_uri = "http://localhost/callback"
        mock_settings.return_value = settings

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "access_token": "ya29.test",
            "refresh_token": "1//test-refresh",
            "expires_in": 3600,
            "scope": "openid email https://www.googleapis.com/auth/calendar.readonly",
            "token_type": "Bearer",
        }

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post.return_value = mock_response
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            result = await gcal_service.exchange_code("test-code")

        assert result["access_token"] == "ya29.test"
        assert result["refresh_token"] == "1//test-refresh"

    @pytest.mark.asyncio
    @patch("app.services.google_calendar.get_settings")
    async def test_raises_on_error(self, mock_settings, gcal_service) -> None:
        settings = MagicMock()
        settings.google_client_id = "client-id"
        settings.google_client_secret = "client-secret"
        settings.google_calendar_oauth_redirect_uri = "http://localhost/callback"
        mock_settings.return_value = settings

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "error": "invalid_grant",
            "error_description": "The code has already been redeemed.",
        }

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post.return_value = mock_response
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            with pytest.raises(ValueError, match="already been redeemed"):
                await gcal_service.exchange_code("bad-code")


class TestGetUserEmail:
    """Tests for get_user_email."""

    @pytest.mark.asyncio
    async def test_returns_email(self, gcal_service) -> None:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"email": "user@example.com"}

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get.return_value = mock_response
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            result = await gcal_service.get_user_email("ya29.test")

        assert result == "user@example.com"

    @pytest.mark.asyncio
    async def test_raises_on_api_error(self, gcal_service) -> None:
        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_response.text = "Unauthorized"

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get.return_value = mock_response
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            with pytest.raises(ValueError, match="401"):
                await gcal_service.get_user_email("invalid-token")


class TestStoreOAuthToken:
    """Tests for store_oauth_token."""

    @pytest.mark.asyncio
    async def test_stores_token_with_email(self, gcal_service) -> None:
        mock_token = MagicMock()
        mock_token.id = "token-id"
        mock_token.provider = PROVIDER
        mock_token.account_label = "personal"
        mock_token.external_account_id = "user@example.com"

        gcal_service.token_encryption.store_encrypted_token.return_value = mock_token

        # Mock get_user_email
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"email": "user@example.com"}

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get.return_value = mock_response
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            result = await gcal_service.store_oauth_token(
                user_id="user-1",
                token_data={
                    "access_token": "ya29.test",
                    "refresh_token": "1//refresh",
                    "expires_in": 3600,
                    "scope": "openid email calendar.readonly",
                },
                account_label="personal",
            )

        assert result.external_account_id == "user@example.com"
        store_call = gcal_service.token_encryption.store_encrypted_token.call_args
        assert store_call[1]["provider"] == PROVIDER
        assert store_call[1]["account_label"] == "personal"
        assert store_call[1]["external_account_id"] == "user@example.com"
        assert store_call[1]["refresh_token"] == "1//refresh"


class TestRefreshAccessToken:
    """Tests for refresh_access_token."""

    @pytest.mark.asyncio
    @patch("app.services.google_calendar.get_settings")
    async def test_refreshes_successfully(self, mock_settings, gcal_service) -> None:
        settings = MagicMock()
        settings.google_client_id = "client-id"
        settings.google_client_secret = "client-secret"
        mock_settings.return_value = settings

        mock_token = MagicMock()
        mock_token.user_id = "user-1"
        mock_token.account_label = "personal"
        mock_token.external_account_id = "user@example.com"

        gcal_service.token_encryption.get_decrypted_refresh_token.return_value = (
            "1//refresh"
        )

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "access_token": "ya29.new-token",
            "expires_in": 3600,
            "scope": "openid email calendar.readonly",
        }

        mock_stored = MagicMock()
        gcal_service.token_encryption.store_encrypted_token.return_value = mock_stored

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post.return_value = mock_response
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            result = await gcal_service.refresh_access_token(mock_token)

        assert result == mock_stored
        store_call = gcal_service.token_encryption.store_encrypted_token.call_args
        assert store_call[1]["access_token"] == "ya29.new-token"
        # Refresh token should be re-used from original
        assert store_call[1]["refresh_token"] == "1//refresh"

    @pytest.mark.asyncio
    async def test_raises_without_refresh_token(self, gcal_service) -> None:
        mock_token = MagicMock()
        gcal_service.token_encryption.get_decrypted_refresh_token.return_value = None

        with pytest.raises(ValueError, match="No refresh token available"):
            await gcal_service.refresh_access_token(mock_token)


class TestGetValidToken:
    """Tests for get_valid_token."""

    @pytest.mark.asyncio
    async def test_returns_token_when_not_expired(self, gcal_service) -> None:
        mock_token = MagicMock()
        mock_token.expires_at = None

        gcal_service.token_repo.get_by_user_provider_and_label.return_value = (
            mock_token
        )
        gcal_service.token_encryption.get_decrypted_access_token.return_value = (
            "ya29.valid"
        )

        result = await gcal_service.get_valid_token("user-1", "default")
        assert result == "ya29.valid"

    @pytest.mark.asyncio
    async def test_returns_none_when_no_token(self, gcal_service) -> None:
        gcal_service.token_repo.get_by_user_provider_and_label.return_value = None
        result = await gcal_service.get_valid_token("user-1")
        assert result is None


class TestDeleteConnection:
    """Tests for delete_connection."""

    @pytest.mark.asyncio
    async def test_deletes_with_revoke(self, gcal_service) -> None:
        mock_token = MagicMock()
        mock_token.user_id = "user-1"
        gcal_service.token_repo.get.return_value = mock_token
        gcal_service.token_encryption.get_decrypted_access_token.return_value = (
            "ya29.test"
        )
        gcal_service.token_repo.delete_by_id.return_value = True

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            result = await gcal_service.delete_connection("token-1", "user-1")

        assert result is True

    @pytest.mark.asyncio
    async def test_returns_false_when_not_found(self, gcal_service) -> None:
        gcal_service.token_repo.get.return_value = None
        result = await gcal_service.delete_connection("nonexistent", "user-1")
        assert result is False

    @pytest.mark.asyncio
    async def test_returns_false_when_wrong_user(self, gcal_service) -> None:
        mock_token = MagicMock()
        mock_token.user_id = "other-user"
        gcal_service.token_repo.get.return_value = mock_token

        result = await gcal_service.delete_connection("token-1", "user-1")
        assert result is False
