"""GitHub service for OAuth, PAT, and API operations."""

import logging
import secrets
import time
from datetime import datetime, UTC
from urllib.parse import urlencode

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.encryption import get_encryption_service
from app.core.oauth_state import store_oauth_state
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

    # --- Installation Token Generation ---

    async def get_installation_token_for_repo(
        self, user_id: str, repo_full_name: str
    ) -> str | None:
        """Get a short-lived installation access token for a specific repo.

        1. Gets the user's OAuth token to list installations.
        2. Finds which installation has access to the repo.
        3. Signs a JWT with the App private key and exchanges it for an
           installation access token (valid ~1 hour).

        Returns None if no installation covers the repo.
        """
        settings = get_settings()
        if not settings.github_app_id or not (
            settings.github_app_private_key or settings.github_app_private_key_file
        ):
            return None

        # Get user's token to find installations
        access_token = await self.get_valid_token(user_id)
        if not access_token:
            return None

        # Find installation for this repo
        installations = await self.get_installations(access_token)
        if not installations:
            return None

        # Check which installation covers this repo
        owner = repo_full_name.split("/")[0]
        installation_id = None
        for inst in installations:
            account = inst.get("account", {})
            if account.get("login", "").lower() == owner.lower():
                installation_id = inst.get("id")
                break

        if not installation_id:
            return None

        return await self._create_installation_token(installation_id)

    async def _create_installation_token(
        self, installation_id: int
    ) -> str:
        """Create an installation access token by signing a JWT.

        Uses the GitHub App's private key to create a JWT, then exchanges
        it for a short-lived installation token via the GitHub API.
        """
        from jose import jwt as jose_jwt

        settings = get_settings()

        # Load private key
        private_key = settings.github_app_private_key
        if not private_key and settings.github_app_private_key_file:
            import pathlib

            private_key = pathlib.Path(
                settings.github_app_private_key_file
            ).read_text()

        if not private_key:
            raise ValueError("GitHub App private key not configured")

        # Create JWT (valid for 10 minutes max per GitHub docs)
        now = int(time.time())
        payload = {
            "iat": now - 60,  # Issued 60s ago to account for clock drift
            "exp": now + (10 * 60),  # Expires in 10 minutes
            "iss": settings.github_app_id,
        }
        encoded_jwt = jose_jwt.encode(payload, private_key, algorithm="RS256")

        # Exchange JWT for installation access token
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{GITHUB_API_URL}/app/installations/{installation_id}/access_tokens",
                headers={
                    "Authorization": f"Bearer {encoded_jwt}",
                    "Accept": "application/vnd.github+json",
                    "X-GitHub-Api-Version": "2022-11-28",
                },
            )

        if response.status_code != 201:
            raise ValueError(
                f"Failed to create installation token: {response.status_code} {response.text}"
            )

        return response.json()["token"]

    async def get_accessible_repos(self, user_id: str) -> list[dict]:
        """List all repos the user's GitHub connections can access.

        For each GitHub connection:
        - If it has App installations, fetches repos per installation
          and includes the installation-level permissions.
        - Falls back to GET /user/repos (works for PATs and OAuth tokens),
          using the token's scope as the permissions indicator.

        Returns a list of dicts:
            {owner, repo_name, full_name, private, account_label,
             permissions, permission_source}
        """
        tokens = await self.token_repo.get_all_by_user_and_provider(user_id, "github")
        if not tokens:
            return []

        repos: list[dict] = []
        seen: set[str] = set()

        def _add_repo(
            repo_data: dict,
            account_label: str,
            permissions: dict[str, str],
            permission_source: str,
        ) -> None:
            full_name = repo_data.get("full_name", "")
            if not full_name or full_name in seen:
                return
            seen.add(full_name)
            owner, _, name = full_name.partition("/")
            repos.append({
                "owner": owner,
                "repo_name": name,
                "full_name": full_name,
                "private": repo_data.get("private", False),
                "account_label": account_label,
                "permissions": permissions,
                "permission_source": permission_source,
            })

        for token_record in tokens:
            access_token = await self.token_encryption.get_decrypted_access_token(
                token_record
            )
            if not access_token:
                continue

            found_via_installation = False

            # Try installation-based repo listing first
            try:
                installations = await self.get_installations(access_token)
                for inst in installations:
                    installation_id = inst.get("id")
                    if not installation_id:
                        continue

                    # Permissions are set at installation level
                    inst_permissions = inst.get("permissions", {})

                    try:
                        inst_repos = await self._get_installation_repos(
                            access_token, installation_id
                        )
                        for repo in inst_repos:
                            _add_repo(
                                repo,
                                token_record.account_label,
                                inst_permissions,
                                "app",
                            )
                        found_via_installation = True
                    except Exception:
                        logger.warning(
                            f"Failed to fetch repos for installation {installation_id}"
                        )
            except Exception:
                logger.debug(
                    f"No installations for account {token_record.account_label}, "
                    "falling back to user repos"
                )

            # Fall back to user repos API (works for PATs and OAuth without App)
            if not found_via_installation:
                # For PATs/OAuth, derive permissions from repo-level fields
                try:
                    user_repos = await self._get_user_repos(access_token)
                    for repo in user_repos:
                        # GitHub user/repos response includes per-repo permissions
                        repo_perms = repo.get("permissions", {})
                        permissions = {}
                        if repo_perms.get("admin"):
                            permissions["administration"] = "write"
                        if repo_perms.get("push"):
                            permissions["contents"] = "write"
                        elif repo_perms.get("pull"):
                            permissions["contents"] = "read"
                        if repo_perms.get("pull"):
                            permissions["metadata"] = "read"
                        _add_repo(
                            repo,
                            token_record.account_label,
                            permissions,
                            "pat" if token_record.token_type == "pat" else "oauth",
                        )
                except Exception:
                    logger.warning(
                        f"Failed to fetch user repos for account {token_record.account_label}"
                    )

        return repos

    async def _get_installation_repos(
        self, access_token: str, installation_id: int
    ) -> list[dict]:
        """Fetch repos accessible to a specific installation (paginated)."""
        all_repos: list[dict] = []
        page = 1

        async with httpx.AsyncClient() as client:
            while True:
                response = await client.get(
                    f"{GITHUB_API_URL}/user/installations/{installation_id}/repositories",
                    headers={
                        "Authorization": f"Bearer {access_token}",
                        "Accept": "application/vnd.github+json",
                        "X-GitHub-Api-Version": "2022-11-28",
                    },
                    params={"per_page": 100, "page": page},
                )

                if response.status_code != 200:
                    raise ValueError(
                        f"GitHub API error: {response.status_code}"
                    )

                data = response.json()
                repos = data.get("repositories", [])
                all_repos.extend(repos)

                if len(repos) < 100:
                    break
                page += 1

        return all_repos

    async def _get_user_repos(self, access_token: str) -> list[dict]:
        """Fetch repos the authenticated user has access to (paginated).

        Works with PATs and OAuth tokens — does not require a GitHub App.
        """
        all_repos: list[dict] = []
        page = 1

        async with httpx.AsyncClient() as client:
            while True:
                response = await client.get(
                    f"{GITHUB_API_URL}/user/repos",
                    headers={
                        "Authorization": f"Bearer {access_token}",
                        "Accept": "application/vnd.github+json",
                        "X-GitHub-Api-Version": "2022-11-28",
                    },
                    params={
                        "per_page": 100,
                        "page": page,
                        "sort": "full_name",
                    },
                )

                if response.status_code != 200:
                    raise ValueError(
                        f"GitHub API error: {response.status_code}"
                    )

                repos = response.json()
                all_repos.extend(repos)

                if len(repos) < 100:
                    break
                page += 1

        return all_repos

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
