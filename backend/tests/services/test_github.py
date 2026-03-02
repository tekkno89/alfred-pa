"""Tests for GitHubService."""

from datetime import datetime, UTC
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.github import GitHubService


@pytest.fixture
def mock_db() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def github_service(mock_db) -> GitHubService:
    """Create a GitHubService with mocked dependencies."""
    svc = GitHubService.__new__(GitHubService)
    svc.db = mock_db
    svc.token_repo = AsyncMock()
    svc.token_encryption = AsyncMock()
    svc.app_config_repo = AsyncMock()
    svc.key_repo = AsyncMock()
    svc._encryption = MagicMock()
    return svc


class TestGetAppCredentials:
    """Tests for _get_app_credentials."""

    @pytest.mark.asyncio
    async def test_returns_per_user_config_when_id_provided(self, github_service) -> None:
        mock_config = MagicMock()
        mock_config.client_id = "per-user-client-id"
        mock_config.encrypted_client_secret = "encrypted-secret"
        mock_config.encryption_key_id = "key-1"

        mock_key = MagicMock()
        mock_key.encrypted_dek = b"dek-bytes"

        github_service.app_config_repo.get.return_value = mock_config
        github_service.key_repo.get.return_value = mock_key
        github_service._encryption.decrypt.return_value = "decrypted-secret"

        client_id, client_secret = await github_service._get_app_credentials("config-1")

        assert client_id == "per-user-client-id"
        assert client_secret == "decrypted-secret"
        github_service._encryption.decrypt.assert_called_once_with(
            "encrypted-secret", b"dek-bytes"
        )

    @pytest.mark.asyncio
    @patch("app.services.github.get_settings")
    async def test_falls_back_to_global_when_no_id(self, mock_settings, github_service) -> None:
        settings = MagicMock()
        settings.github_client_id = "global-client-id"
        settings.github_client_secret = "global-secret"
        mock_settings.return_value = settings

        client_id, client_secret = await github_service._get_app_credentials(None)

        assert client_id == "global-client-id"
        assert client_secret == "global-secret"

    @pytest.mark.asyncio
    @patch("app.services.github.get_settings")
    async def test_falls_back_to_global_when_config_not_found(self, mock_settings, github_service) -> None:
        settings = MagicMock()
        settings.github_client_id = "global-client-id"
        settings.github_client_secret = "global-secret"
        mock_settings.return_value = settings

        github_service.app_config_repo.get.return_value = None

        client_id, client_secret = await github_service._get_app_credentials("nonexistent")

        assert client_id == "global-client-id"
        assert client_secret == "global-secret"

    @pytest.mark.asyncio
    @patch("app.services.github.get_settings")
    async def test_raises_when_no_config_available(self, mock_settings, github_service) -> None:
        settings = MagicMock()
        settings.github_client_id = ""
        settings.github_client_secret = ""
        mock_settings.return_value = settings

        with pytest.raises(ValueError, match="No GitHub App configured"):
            await github_service._get_app_credentials(None)


class TestGetOAuthUrl:
    """Tests for get_oauth_url."""

    @pytest.mark.asyncio
    @patch("app.services.github.get_settings")
    async def test_generates_url_with_state(self, mock_settings, github_service) -> None:
        settings = MagicMock()
        settings.github_client_id = "test-client-id"
        settings.github_client_secret = "test-secret"
        settings.github_oauth_redirect_uri = "http://localhost:8000/api/github/oauth/callback"
        mock_settings.return_value = settings

        url = await github_service.get_oauth_url("user-1", "personal")

        assert "client_id=test-client-id" in url
        assert "github.com/login/oauth/authorize" in url
        assert "state=" in url

    @pytest.mark.asyncio
    @patch("app.services.github.get_settings")
    async def test_raises_if_not_configured(self, mock_settings, github_service) -> None:
        settings = MagicMock()
        settings.github_client_id = ""
        settings.github_client_secret = ""
        mock_settings.return_value = settings

        with pytest.raises(ValueError, match="No GitHub App configured"):
            await github_service.get_oauth_url("user-1")

    @pytest.mark.asyncio
    @patch("app.services.github.get_settings")
    async def test_uses_per_user_config(self, mock_settings, github_service) -> None:
        settings = MagicMock()
        settings.github_oauth_redirect_uri = "http://localhost:8000/api/github/oauth/callback"
        mock_settings.return_value = settings

        mock_config = MagicMock()
        mock_config.client_id = "per-user-id"
        mock_config.encrypted_client_secret = "enc"
        mock_config.encryption_key_id = "key-1"

        mock_key = MagicMock()
        mock_key.encrypted_dek = b"dek"

        github_service.app_config_repo.get.return_value = mock_config
        github_service.key_repo.get.return_value = mock_key
        github_service._encryption.decrypt.return_value = "secret"

        url = await github_service.get_oauth_url("user-1", app_config_id="config-1")

        assert "client_id=per-user-id" in url


class TestExchangeCode:
    """Tests for exchange_code."""

    @pytest.mark.asyncio
    @patch("app.services.github.get_settings")
    async def test_exchanges_code_successfully(self, mock_settings, github_service) -> None:
        settings = MagicMock()
        settings.github_client_id = "client-id"
        settings.github_client_secret = "client-secret"
        mock_settings.return_value = settings

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "access_token": "gho_test123",
            "token_type": "bearer",
            "scope": "repo,read:user",
        }

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post.return_value = mock_response
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            result = await github_service.exchange_code("test-code")

        assert result["access_token"] == "gho_test123"

    @pytest.mark.asyncio
    @patch("app.services.github.get_settings")
    async def test_raises_on_error(self, mock_settings, github_service) -> None:
        settings = MagicMock()
        settings.github_client_id = "client-id"
        settings.github_client_secret = "client-secret"
        mock_settings.return_value = settings

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "error": "bad_verification_code",
            "error_description": "The code passed is incorrect or expired.",
        }

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post.return_value = mock_response
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            with pytest.raises(ValueError, match="incorrect or expired"):
                await github_service.exchange_code("bad-code")

    @pytest.mark.asyncio
    async def test_exchange_code_with_app_config(self, github_service) -> None:
        mock_config = MagicMock()
        mock_config.client_id = "per-user-id"
        mock_config.encrypted_client_secret = "enc"
        mock_config.encryption_key_id = "key-1"

        mock_key = MagicMock()
        mock_key.encrypted_dek = b"dek"

        github_service.app_config_repo.get.return_value = mock_config
        github_service.key_repo.get.return_value = mock_key
        github_service._encryption.decrypt.return_value = "per-user-secret"

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "access_token": "gho_peruser",
            "token_type": "bearer",
        }

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post.return_value = mock_response
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            result = await github_service.exchange_code("code", app_config_id="config-1")

        assert result["access_token"] == "gho_peruser"
        # Verify the per-user credentials were used
        call_kwargs = mock_client.post.call_args
        assert call_kwargs[1]["data"]["client_id"] == "per-user-id"
        assert call_kwargs[1]["data"]["client_secret"] == "per-user-secret"


class TestRefreshToken:
    """Tests for refresh_token with per-user app config."""

    @pytest.mark.asyncio
    async def test_refresh_uses_token_app_config(self, github_service) -> None:
        mock_token = MagicMock()
        mock_token.user_id = "user-1"
        mock_token.account_label = "work"
        mock_token.external_account_id = "octocat"
        mock_token.github_app_config_id = "config-1"

        mock_config = MagicMock()
        mock_config.client_id = "per-user-id"
        mock_config.encrypted_client_secret = "enc"
        mock_config.encryption_key_id = "key-1"

        mock_key = MagicMock()
        mock_key.encrypted_dek = b"dek"

        github_service.app_config_repo.get.return_value = mock_config
        github_service.key_repo.get.return_value = mock_key
        github_service._encryption.decrypt.return_value = "per-user-secret"
        github_service.token_encryption.get_decrypted_refresh_token.return_value = "refresh-tok"

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "access_token": "new-access",
            "refresh_token": "new-refresh",
            "scope": "repo",
        }

        mock_stored_token = MagicMock()
        github_service.token_encryption.store_encrypted_token.return_value = mock_stored_token

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post.return_value = mock_response
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            result = await github_service.refresh_token(mock_token)

        assert result == mock_stored_token
        # Verify app_config_id is passed through
        store_call = github_service.token_encryption.store_encrypted_token.call_args
        assert store_call[1]["github_app_config_id"] == "config-1"


class TestStorePAT:
    """Tests for store_pat."""

    @pytest.mark.asyncio
    async def test_stores_pat_with_username(self, github_service) -> None:
        mock_token = MagicMock()
        mock_token.id = "token-id"
        mock_token.provider = "github"
        mock_token.account_label = "work"
        mock_token.external_account_id = "octocat"
        mock_token.token_type = "pat"
        mock_token.scope = "pat"
        mock_token.expires_at = None
        mock_token.created_at = datetime.now(UTC)

        github_service.token_encryption.store_encrypted_token.return_value = mock_token

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"login": "octocat"}

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get.return_value = mock_response
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            result = await github_service.store_pat("user-1", "ghp_test123", "work")

        assert result.external_account_id == "octocat"
        assert result.token_type == "pat"
        github_service.token_encryption.store_encrypted_token.assert_called_once()

    @pytest.mark.asyncio
    async def test_invalid_pat_raises(self, github_service) -> None:
        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_response.text = "Bad credentials"

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get.return_value = mock_response
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            with pytest.raises(ValueError, match="401"):
                await github_service.store_pat("user-1", "ghp_invalid")


class TestGetValidToken:
    """Tests for get_valid_token."""

    @pytest.mark.asyncio
    async def test_returns_token_when_valid(self, github_service) -> None:
        mock_token = MagicMock()
        mock_token.expires_at = None  # PAT, no expiry
        mock_token.token_type = "pat"

        github_service.token_repo.get_by_user_provider_and_label.return_value = mock_token
        github_service.token_encryption.get_decrypted_access_token.return_value = "ghp_test"

        result = await github_service.get_valid_token("user-1", "default")
        assert result == "ghp_test"

    @pytest.mark.asyncio
    async def test_returns_none_when_no_token(self, github_service) -> None:
        github_service.token_repo.get_by_user_provider_and_label.return_value = None
        result = await github_service.get_valid_token("user-1")
        assert result is None


class TestRevokeToken:
    """Tests for revoke_token."""

    @pytest.mark.asyncio
    async def test_revoke_deletes_token(self, github_service) -> None:
        mock_token = MagicMock()
        mock_token.github_app_config_id = None
        github_service.token_repo.get_by_user_provider_and_label.return_value = mock_token
        github_service.token_encryption.get_decrypted_access_token.return_value = "ghp_test"

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            with patch("app.services.github.get_settings") as mock_settings:
                settings = MagicMock()
                settings.github_client_id = "client-id"
                settings.github_client_secret = "secret"
                mock_settings.return_value = settings

                result = await github_service.revoke_token("user-1")

        assert result is True
        github_service.token_repo.delete.assert_called_once_with(mock_token)

    @pytest.mark.asyncio
    async def test_revoke_returns_false_when_no_token(self, github_service) -> None:
        github_service.token_repo.get_by_user_provider_and_label.return_value = None
        result = await github_service.revoke_token("user-1")
        assert result is False


class TestAppConfigCRUD:
    """Tests for app config create/list/delete."""

    @pytest.mark.asyncio
    @patch("app.services.github.get_settings")
    async def test_create_app_config(self, mock_settings, github_service) -> None:
        settings = MagicMock()
        settings.encryption_kek_provider = "local"
        mock_settings.return_value = settings

        mock_key = MagicMock()
        mock_key.id = "key-1"
        mock_key.encrypted_dek = b"dek-bytes"
        github_service.key_repo.get_active_by_name.return_value = mock_key
        github_service._encryption.encrypt.return_value = "encrypted-secret"

        mock_config = MagicMock()
        mock_config.id = "config-1"
        mock_config.label = "Work"
        mock_config.client_id = "Iv1.abc"
        mock_config.github_app_id = None
        mock_config.created_at = datetime.now(UTC)
        github_service.app_config_repo.create_config.return_value = mock_config

        result = await github_service.create_app_config(
            user_id="user-1",
            label="Work",
            client_id="Iv1.abc",
            client_secret="super-secret",
        )

        assert result.label == "Work"
        github_service._encryption.encrypt.assert_called_once_with("super-secret", b"dek-bytes")
        github_service.app_config_repo.create_config.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_app_configs(self, github_service) -> None:
        mock_configs = [MagicMock(), MagicMock()]
        github_service.app_config_repo.get_all_by_user.return_value = mock_configs

        result = await github_service.get_app_configs("user-1")
        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_delete_app_config(self, github_service) -> None:
        github_service.app_config_repo.delete_by_id.return_value = True
        result = await github_service.delete_app_config("config-1", "user-1")
        assert result is True

    @pytest.mark.asyncio
    async def test_delete_app_config_not_found(self, github_service) -> None:
        github_service.app_config_repo.delete_by_id.return_value = False
        result = await github_service.delete_app_config("nonexistent", "user-1")
        assert result is False
