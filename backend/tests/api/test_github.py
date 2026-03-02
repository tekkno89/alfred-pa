"""Tests for GitHub API endpoints."""

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


class TestGitHubOAuthUrl:
    """Tests for GET /github/oauth/url."""

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
        with patch("app.api.github.GitHubService") as mock_svc_cls:
            mock_svc = AsyncMock()
            mock_svc.get_oauth_url.return_value = (
                "https://github.com/login/oauth/authorize?client_id=test-client-id&state=abc"
            )
            mock_svc_cls.return_value = mock_svc

            response = await client.get("/api/github/oauth/url")

        assert response.status_code == 200
        data = response.json()
        assert "url" in data
        assert "github.com/login/oauth/authorize" in data["url"]

    async def test_returns_error_when_not_configured(self, client):
        with patch("app.api.github.GitHubService") as mock_svc_cls:
            mock_svc = AsyncMock()
            mock_svc.get_oauth_url.side_effect = ValueError("No GitHub App configured")
            mock_svc_cls.return_value = mock_svc

            response = await client.get("/api/github/oauth/url")

        assert response.status_code == 400

    async def test_passes_app_config_id(self, client):
        with patch("app.api.github.GitHubService") as mock_svc_cls:
            mock_svc = AsyncMock()
            mock_svc.get_oauth_url.return_value = "https://github.com/login/oauth/authorize?state=abc"
            mock_svc_cls.return_value = mock_svc

            response = await client.get(
                "/api/github/oauth/url?app_config_id=config-1"
            )

        assert response.status_code == 200
        mock_svc.get_oauth_url.assert_called_once_with(
            "test-user-id", "default", app_config_id="config-1"
        )


class TestGitHubConnections:
    """Tests for GET /github/connections."""

    @pytest_asyncio.fixture
    async def client(self, mock_user):
        app.dependency_overrides[get_current_user] = lambda: mock_user
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as ac:
            yield ac
        app.dependency_overrides.clear()

    async def test_list_connections_empty(self, client, mock_user):
        with patch("app.api.github.OAuthTokenRepository") as mock_repo_cls:
            mock_repo = AsyncMock()
            mock_repo.get_all_by_user_and_provider.return_value = []
            mock_repo_cls.return_value = mock_repo

            response = await client.get("/api/github/connections")

        assert response.status_code == 200
        data = response.json()
        assert data["connections"] == []

    async def test_list_connections_with_data(self, client, mock_user):
        mock_token = MagicMock()
        mock_token.id = "token-1"
        mock_token.provider = "github"
        mock_token.account_label = "personal"
        mock_token.external_account_id = "octocat"
        mock_token.token_type = "pat"
        mock_token.scope = "repo"
        mock_token.expires_at = None
        mock_token.created_at = datetime(2026, 1, 1, tzinfo=UTC)
        mock_token.github_app_config_id = None

        with patch("app.api.github.OAuthTokenRepository") as mock_repo_cls:
            mock_repo = AsyncMock()
            mock_repo.get_all_by_user_and_provider.return_value = [mock_token]
            mock_repo_cls.return_value = mock_repo

            response = await client.get("/api/github/connections")

        assert response.status_code == 200
        data = response.json()
        assert len(data["connections"]) == 1
        assert data["connections"][0]["external_account_id"] == "octocat"
        assert data["connections"][0]["token_type"] == "pat"
        assert data["connections"][0]["app_config_id"] is None
        assert data["connections"][0]["app_config_label"] is None

    async def test_list_connections_with_app_config_label(self, client, mock_user):
        mock_token = MagicMock()
        mock_token.id = "token-1"
        mock_token.provider = "github"
        mock_token.account_label = "work"
        mock_token.external_account_id = "octocat"
        mock_token.token_type = "oauth"
        mock_token.scope = "repo"
        mock_token.expires_at = None
        mock_token.created_at = datetime(2026, 1, 1, tzinfo=UTC)
        mock_token.github_app_config_id = "config-1"

        mock_config = MagicMock()
        mock_config.label = "Work App"

        with patch("app.api.github.OAuthTokenRepository") as mock_repo_cls, \
             patch("app.api.github.GitHubAppConfigRepository") as mock_config_repo_cls:
            mock_repo = AsyncMock()
            mock_repo.get_all_by_user_and_provider.return_value = [mock_token]
            mock_repo_cls.return_value = mock_repo

            mock_config_repo = AsyncMock()
            mock_config_repo.get.return_value = mock_config
            mock_config_repo_cls.return_value = mock_config_repo

            response = await client.get("/api/github/connections")

        assert response.status_code == 200
        data = response.json()
        assert data["connections"][0]["app_config_id"] == "config-1"
        assert data["connections"][0]["app_config_label"] == "Work App"


class TestAddGitHubPAT:
    """Tests for POST /github/connections/pat."""

    @pytest_asyncio.fixture
    async def client(self, mock_user):
        app.dependency_overrides[get_current_user] = lambda: mock_user
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as ac:
            yield ac
        app.dependency_overrides.clear()

    async def test_add_pat_success(self, client, mock_user):
        mock_token = MagicMock()
        mock_token.id = "token-1"
        mock_token.provider = "github"
        mock_token.account_label = "work"
        mock_token.external_account_id = "octocat"
        mock_token.token_type = "pat"
        mock_token.scope = "pat"
        mock_token.expires_at = None
        mock_token.created_at = datetime(2026, 1, 1, tzinfo=UTC)

        with patch("app.api.github.GitHubService") as mock_svc_cls:
            mock_svc = AsyncMock()
            mock_svc.store_pat.return_value = mock_token
            mock_svc_cls.return_value = mock_svc

            response = await client.post(
                "/api/github/connections/pat",
                json={"token": "ghp_test123", "account_label": "work"},
            )

        assert response.status_code == 201
        data = response.json()
        assert data["token_type"] == "pat"
        assert data["account_label"] == "work"

    async def test_add_pat_invalid_token(self, client, mock_user):
        with patch("app.api.github.GitHubService") as mock_svc_cls:
            mock_svc = AsyncMock()
            mock_svc.store_pat.side_effect = ValueError("401 Bad credentials")
            mock_svc_cls.return_value = mock_svc

            response = await client.post(
                "/api/github/connections/pat",
                json={"token": "ghp_invalid", "account_label": "default"},
            )

        assert response.status_code == 400

    async def test_add_pat_empty_token_rejected(self, client, mock_user):
        response = await client.post(
            "/api/github/connections/pat",
            json={"token": "", "account_label": "default"},
        )
        assert response.status_code == 422


class TestDeleteGitHubConnection:
    """Tests for DELETE /github/connections/{id}."""

    @pytest_asyncio.fixture
    async def client(self, mock_user):
        app.dependency_overrides[get_current_user] = lambda: mock_user
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as ac:
            yield ac
        app.dependency_overrides.clear()

    async def test_delete_connection_success(self, client, mock_user):
        with patch("app.api.github.GitHubService") as mock_svc_cls:
            mock_svc = AsyncMock()
            mock_svc.delete_connection.return_value = True
            mock_svc_cls.return_value = mock_svc

            response = await client.delete("/api/github/connections/token-1")

        assert response.status_code == 204

    async def test_delete_connection_not_found(self, client, mock_user):
        with patch("app.api.github.GitHubService") as mock_svc_cls:
            mock_svc = AsyncMock()
            mock_svc.delete_connection.return_value = False
            mock_svc_cls.return_value = mock_svc

            response = await client.delete("/api/github/connections/nonexistent")

        assert response.status_code == 404


class TestGitHubAppConfigs:
    """Tests for app config endpoints."""

    @pytest_asyncio.fixture
    async def client(self, mock_user):
        app.dependency_overrides[get_current_user] = lambda: mock_user
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as ac:
            yield ac
        app.dependency_overrides.clear()

    async def test_list_app_configs(self, client, mock_user):
        mock_config = MagicMock()
        mock_config.id = "config-1"
        mock_config.label = "Work"
        mock_config.client_id = "Iv1.abc"
        mock_config.github_app_id = None
        mock_config.created_at = datetime(2026, 1, 1, tzinfo=UTC)

        with patch("app.api.github.GitHubService") as mock_svc_cls:
            mock_svc = AsyncMock()
            mock_svc.get_app_configs.return_value = [mock_config]
            mock_svc_cls.return_value = mock_svc

            response = await client.get("/api/github/app-configs")

        assert response.status_code == 200
        data = response.json()
        assert len(data["configs"]) == 1
        assert data["configs"][0]["label"] == "Work"
        assert data["configs"][0]["client_id"] == "Iv1.abc"

    async def test_create_app_config(self, client, mock_user):
        mock_config = MagicMock()
        mock_config.id = "config-1"
        mock_config.label = "Personal"
        mock_config.client_id = "Iv1.xyz"
        mock_config.github_app_id = "12345"
        mock_config.created_at = datetime(2026, 1, 1, tzinfo=UTC)

        with patch("app.api.github.GitHubService") as mock_svc_cls:
            mock_svc = AsyncMock()
            mock_svc.create_app_config.return_value = mock_config
            mock_svc_cls.return_value = mock_svc

            response = await client.post(
                "/api/github/app-configs",
                json={
                    "label": "Personal",
                    "client_id": "Iv1.xyz",
                    "client_secret": "super-secret",
                    "github_app_id": "12345",
                },
            )

        assert response.status_code == 201
        data = response.json()
        assert data["label"] == "Personal"
        assert data["client_id"] == "Iv1.xyz"
        # Verify secret is NOT in response
        assert "client_secret" not in data
        assert "encrypted_client_secret" not in data

    async def test_create_app_config_missing_fields(self, client, mock_user):
        response = await client.post(
            "/api/github/app-configs",
            json={"label": "Test"},
        )
        assert response.status_code == 422

    async def test_delete_app_config_success(self, client, mock_user):
        with patch("app.api.github.GitHubService") as mock_svc_cls:
            mock_svc = AsyncMock()
            mock_svc.delete_app_config.return_value = True
            mock_svc_cls.return_value = mock_svc

            response = await client.delete("/api/github/app-configs/config-1")

        assert response.status_code == 204

    async def test_delete_app_config_not_found(self, client, mock_user):
        with patch("app.api.github.GitHubService") as mock_svc_cls:
            mock_svc = AsyncMock()
            mock_svc.delete_app_config.return_value = False
            mock_svc_cls.return_value = mock_svc

            response = await client.delete("/api/github/app-configs/nonexistent")

        assert response.status_code == 404
