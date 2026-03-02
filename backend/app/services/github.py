"""GitHub service for OAuth, PAT, and API operations."""

import logging
import secrets
from datetime import datetime, UTC
from urllib.parse import urlencode

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.encryption import get_encryption_service
from app.core.oauth_state import consume_oauth_state, store_oauth_state
from app.db.models import UserOAuthToken
from app.db.models.github_app_config import GitHubAppConfig
from app.db.repositories import (
    EncryptionKeyRepository,
    GitHubAppConfigRepository,
    OAuthTokenRepository,
)
from app.services.token_encryption import TokenEncryptionService

logger = logging.getLogger(__name__)

GITHUB_AUTHORIZE_URL = "https://github.com/login/oauth/authorize"
GITHUB_TOKEN_URL = "https://github.com/login/oauth/access_token"
GITHUB_API_URL = "https://api.github.com"


class GitHubService:
    """Service for GitHub OAuth and API operations."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.token_repo = OAuthTokenRepository(db)
        self.token_encryption = TokenEncryptionService(db)
        self.app_config_repo = GitHubAppConfigRepository(db)
        self.key_repo = EncryptionKeyRepository(db)
        self._encryption = get_encryption_service()

    async def _get_app_credentials(
        self, app_config_id: str | None = None
    ) -> tuple[str, str]:
        """Get GitHub App client_id and client_secret.

        Looks up per-user app config if app_config_id is provided,
        otherwise falls back to global env vars.

        Returns (client_id, client_secret).
        Raises ValueError if no credentials are available.
        """
        if app_config_id:
            config = await self.app_config_repo.get(app_config_id)
            if config:
                # Decrypt the client secret
                key = await self.key_repo.get(config.encryption_key_id)
                if not key:
                    raise ValueError("Encryption key not found for app config")
                client_secret = self._encryption.decrypt(
                    config.encrypted_client_secret, key.encrypted_dek
                )
                return config.client_id, client_secret

        # Fall back to global config
        settings = get_settings()
        if settings.github_client_id and settings.github_client_secret:
            return settings.github_client_id, settings.github_client_secret

        raise ValueError("No GitHub App configured")

    async def get_oauth_url(
        self,
        user_id: str,
        account_label: str = "default",
        app_config_id: str | None = None,
    ) -> str:
        """Generate GitHub OAuth authorization URL."""
        client_id, _ = await self._get_app_credentials(app_config_id)

        settings = get_settings()
        state = secrets.token_urlsafe(32)
        store_oauth_state(state, user_id, account_label, app_config_id=app_config_id)

        params = {
            "client_id": client_id,
            "redirect_uri": settings.github_oauth_redirect_uri,
            "scope": "repo,read:user,user:email",
            "state": state,
        }

        return f"{GITHUB_AUTHORIZE_URL}?{urlencode(params)}"

    async def exchange_code(
        self, code: str, app_config_id: str | None = None
    ) -> dict:
        """Exchange OAuth authorization code for access token."""
        client_id, client_secret = await self._get_app_credentials(app_config_id)

        async with httpx.AsyncClient() as client:
            response = await client.post(
                GITHUB_TOKEN_URL,
                data={
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "code": code,
                },
                headers={"Accept": "application/json"},
            )

        data = response.json()
        if "error" in data:
            raise ValueError(f"GitHub OAuth error: {data.get('error_description', data['error'])}")

        return data

    async def refresh_token(self, token: UserOAuthToken) -> UserOAuthToken:
        """Refresh a GitHub App OAuth token (tokens expire in 8 hours)."""
        client_id, client_secret = await self._get_app_credentials(
            token.github_app_config_id
        )

        refresh_token = await self.token_encryption.get_decrypted_refresh_token(token)
        if not refresh_token:
            raise ValueError("No refresh token available")

        async with httpx.AsyncClient() as client:
            response = await client.post(
                GITHUB_TOKEN_URL,
                data={
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "grant_type": "refresh_token",
                    "refresh_token": refresh_token,
                },
                headers={"Accept": "application/json"},
            )

        data = response.json()
        if "error" in data:
            raise ValueError(f"Token refresh failed: {data.get('error_description', data['error'])}")

        # Calculate expiration
        expires_at = None
        if "expires_in" in data:
            from datetime import timedelta

            expires_at = datetime.now(UTC).replace(tzinfo=None) + timedelta(
                seconds=data["expires_in"]
            )

        # Store new tokens
        return await self.token_encryption.store_encrypted_token(
            user_id=token.user_id,
            provider="github",
            access_token=data["access_token"],
            refresh_token=data.get("refresh_token"),
            scope=data.get("scope"),
            expires_at=expires_at,
            account_label=token.account_label,
            external_account_id=token.external_account_id,
            github_app_config_id=token.github_app_config_id,
        )

    async def store_oauth_token(
        self,
        user_id: str,
        token_data: dict,
        account_label: str = "default",
        app_config_id: str | None = None,
    ) -> UserOAuthToken:
        """Store GitHub OAuth token after code exchange."""
        access_token = token_data["access_token"]
        refresh_token = token_data.get("refresh_token")
        scope = token_data.get("scope")

        # Calculate expiration if provided
        expires_at = None
        if "expires_in" in token_data:
            from datetime import timedelta

            expires_at = datetime.now(UTC).replace(tzinfo=None) + timedelta(
                seconds=token_data["expires_in"]
            )

        # Get the GitHub username
        user_info = await self.get_authenticated_user(access_token)
        github_username = user_info.get("login")

        return await self.token_encryption.store_encrypted_token(
            user_id=user_id,
            provider="github",
            access_token=access_token,
            refresh_token=refresh_token,
            scope=scope,
            expires_at=expires_at,
            account_label=account_label,
            external_account_id=github_username,
            github_app_config_id=app_config_id,
        )

    async def store_pat(
        self,
        user_id: str,
        pat: str,
        account_label: str = "default",
    ) -> UserOAuthToken:
        """Store a manually provided personal access token."""
        # Validate the PAT by making an API call
        user_info = await self.get_authenticated_user(pat)
        github_username = user_info.get("login")

        return await self.token_encryption.store_encrypted_token(
            user_id=user_id,
            provider="github",
            access_token=pat,
            scope="pat",
            account_label=account_label,
            external_account_id=github_username,
            token_type="pat",
        )

    async def get_valid_token(
        self, user_id: str, account_label: str = "default"
    ) -> str | None:
        """Get a valid access token, auto-refreshing if expired."""
        token = await self.token_repo.get_by_user_provider_and_label(
            user_id, "github", account_label
        )
        if not token:
            return None

        # Check if token is expired and has a refresh token
        if (
            token.expires_at
            and token.expires_at < datetime.now(UTC).replace(tzinfo=None)
            and token.token_type != "pat"
        ):
            try:
                token = await self.refresh_token(token)
            except ValueError:
                logger.warning(f"Failed to refresh GitHub token for user {user_id}")
                return None

        return await self.token_encryption.get_decrypted_access_token(token)

    async def get_authenticated_user(self, access_token: str) -> dict:
        """Get the authenticated GitHub user info."""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{GITHUB_API_URL}/user",
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Accept": "application/vnd.github+json",
                    "X-GitHub-Api-Version": "2022-11-28",
                },
            )

        if response.status_code != 200:
            raise ValueError(f"GitHub API error: {response.status_code} {response.text}")

        return response.json()

    async def get_installations(self, access_token: str) -> list[dict]:
        """Get GitHub App installations for the authenticated user."""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{GITHUB_API_URL}/user/installations",
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Accept": "application/vnd.github+json",
                    "X-GitHub-Api-Version": "2022-11-28",
                },
            )

        if response.status_code != 200:
            raise ValueError(f"GitHub API error: {response.status_code}")

        return response.json().get("installations", [])

    async def revoke_token(
        self, user_id: str, account_label: str = "default"
    ) -> bool:
        """Revoke and delete a GitHub token."""
        token = await self.token_repo.get_by_user_provider_and_label(
            user_id, "github", account_label
        )
        if not token:
            return False

        # Try to revoke the token with GitHub (best effort)
        try:
            access_token = await self.token_encryption.get_decrypted_access_token(
                token
            )
            client_id, client_secret = await self._get_app_credentials(
                token.github_app_config_id
            )
            async with httpx.AsyncClient() as client:
                await client.delete(
                    f"{GITHUB_API_URL}/applications/{client_id}/token",
                    auth=(client_id, client_secret),
                    json={"access_token": access_token},
                )
        except Exception:
            logger.warning("Failed to revoke GitHub token (best effort)")

        await self.token_repo.delete(token)
        return True

    async def delete_connection(self, connection_id: str, user_id: str) -> bool:
        """Delete a GitHub connection by ID with ownership check."""
        return await self.token_repo.delete_by_id(connection_id, user_id)

    # --- App Config Management ---

    async def create_app_config(
        self,
        user_id: str,
        label: str,
        client_id: str,
        client_secret: str,
        github_app_id: str | None = None,
    ) -> GitHubAppConfig:
        """Create a per-user GitHub App configuration with encrypted client_secret."""
        from app.services.token_encryption import DEK_KEY_NAME

        # Get or create DEK
        key = await self.key_repo.get_active_by_name(DEK_KEY_NAME)
        if key:
            key_id, encrypted_dek = key.id, key.encrypted_dek
        else:
            settings = get_settings()
            encrypted_dek, _ = self._encryption.generate_dek()
            key = await self.key_repo.create_key(
                key_name=DEK_KEY_NAME,
                encrypted_dek=encrypted_dek,
                kek_provider=settings.encryption_kek_provider,
            )
            key_id = key.id

        encrypted_client_secret = self._encryption.encrypt(client_secret, encrypted_dek)

        return await self.app_config_repo.create_config(
            user_id=user_id,
            label=label,
            client_id=client_id,
            encrypted_client_secret=encrypted_client_secret,
            encryption_key_id=key_id,
            github_app_id=github_app_id,
        )

    async def get_app_configs(self, user_id: str) -> list:
        """Get all GitHub App configs for a user."""
        return await self.app_config_repo.get_all_by_user(user_id)

    async def delete_app_config(self, config_id: str, user_id: str) -> bool:
        """Delete a GitHub App config with ownership check."""
        return await self.app_config_repo.delete_by_id(config_id, user_id)
