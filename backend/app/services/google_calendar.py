"""Google Calendar service for OAuth and API operations."""

import logging
import secrets
from datetime import datetime, UTC, timedelta
from urllib.parse import urlencode

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.oauth_state import consume_oauth_state, store_oauth_state
from app.db.models import UserOAuthToken
from app.db.repositories import OAuthTokenRepository
from app.services.token_encryption import TokenEncryptionService

logger = logging.getLogger(__name__)

GOOGLE_AUTHORIZE_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v2/userinfo"
GOOGLE_REVOKE_URL = "https://oauth2.googleapis.com/revoke"

GOOGLE_CALENDAR_SCOPES = "openid email https://www.googleapis.com/auth/calendar"

PROVIDER = "google_calendar"


class GoogleCalendarService:
    """Service for Google Calendar OAuth operations."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.token_repo = OAuthTokenRepository(db)
        self.token_encryption = TokenEncryptionService(db)

    def get_oauth_url(self, user_id: str, account_label: str = "default") -> str:
        """Generate Google OAuth authorization URL."""
        settings = get_settings()

        if not settings.google_client_id:
            raise ValueError("Google OAuth is not configured")

        state = secrets.token_urlsafe(32)
        store_oauth_state(state, user_id, account_label)

        params = {
            "client_id": settings.google_client_id,
            "redirect_uri": settings.google_calendar_oauth_redirect_uri,
            "response_type": "code",
            "scope": GOOGLE_CALENDAR_SCOPES,
            "access_type": "offline",
            "prompt": "consent",
            "state": state,
        }

        return f"{GOOGLE_AUTHORIZE_URL}?{urlencode(params)}"

    async def exchange_code(self, code: str) -> dict:
        """Exchange OAuth authorization code for access/refresh tokens."""
        settings = get_settings()

        async with httpx.AsyncClient() as client:
            response = await client.post(
                GOOGLE_TOKEN_URL,
                data={
                    "client_id": settings.google_client_id,
                    "client_secret": settings.google_client_secret,
                    "code": code,
                    "grant_type": "authorization_code",
                    "redirect_uri": settings.google_calendar_oauth_redirect_uri,
                },
            )

        data = response.json()
        if "error" in data:
            raise ValueError(
                f"Google OAuth error: {data.get('error_description', data['error'])}"
            )

        return data

    async def get_user_email(self, access_token: str) -> str:
        """Get the authenticated user's email address."""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                GOOGLE_USERINFO_URL,
                headers={"Authorization": f"Bearer {access_token}"},
            )

        if response.status_code != 200:
            raise ValueError(
                f"Google API error: {response.status_code} {response.text}"
            )

        return response.json().get("email", "")

    async def store_oauth_token(
        self,
        user_id: str,
        token_data: dict,
        account_label: str = "default",
    ) -> UserOAuthToken:
        """Store Google Calendar OAuth token after code exchange."""
        access_token = token_data["access_token"]
        refresh_token = token_data.get("refresh_token")
        scope = token_data.get("scope")

        expires_at = None
        if "expires_in" in token_data:
            expires_at = datetime.now(UTC).replace(tzinfo=None) + timedelta(
                seconds=token_data["expires_in"]
            )

        email = await self.get_user_email(access_token)

        return await self.token_encryption.store_encrypted_token(
            user_id=user_id,
            provider=PROVIDER,
            access_token=access_token,
            refresh_token=refresh_token,
            scope=scope,
            expires_at=expires_at,
            account_label=account_label,
            external_account_id=email,
        )

    async def refresh_access_token(self, token: UserOAuthToken) -> UserOAuthToken:
        """Refresh an expired access token using the stored refresh token."""
        settings = get_settings()

        refresh_token = await self.token_encryption.get_decrypted_refresh_token(token)
        if not refresh_token:
            raise ValueError("No refresh token available")

        async with httpx.AsyncClient() as client:
            response = await client.post(
                GOOGLE_TOKEN_URL,
                data={
                    "client_id": settings.google_client_id,
                    "client_secret": settings.google_client_secret,
                    "grant_type": "refresh_token",
                    "refresh_token": refresh_token,
                },
            )

        data = response.json()
        if "error" in data:
            raise ValueError(
                f"Token refresh failed: {data.get('error_description', data['error'])}"
            )

        expires_at = None
        if "expires_in" in data:
            expires_at = datetime.now(UTC).replace(tzinfo=None) + timedelta(
                seconds=data["expires_in"]
            )

        # Google refresh responses don't include a new refresh_token,
        # so re-use the existing one
        return await self.token_encryption.store_encrypted_token(
            user_id=token.user_id,
            provider=PROVIDER,
            access_token=data["access_token"],
            refresh_token=refresh_token,
            scope=data.get("scope"),
            expires_at=expires_at,
            account_label=token.account_label,
            external_account_id=token.external_account_id,
        )

    async def get_valid_token(
        self, user_id: str, account_label: str = "default"
    ) -> str | None:
        """Get a valid access token, auto-refreshing if expired."""
        token = await self.token_repo.get_by_user_provider_and_label(
            user_id, PROVIDER, account_label
        )
        if not token:
            return None

        if token.expires_at and token.expires_at < datetime.now(UTC).replace(
            tzinfo=None
        ):
            try:
                token = await self.refresh_access_token(token)
            except ValueError:
                logger.warning(
                    f"Failed to refresh Google Calendar token for user {user_id}"
                )
                return None

        return await self.token_encryption.get_decrypted_access_token(token)

    async def delete_connection(self, connection_id: str, user_id: str) -> bool:
        """Delete a Google Calendar connection by ID with ownership check.

        Best-effort revoke the token with Google before deleting.
        """
        token = await self.token_repo.get(connection_id)
        if not token or token.user_id != user_id:
            return False

        # Best-effort revoke
        try:
            access_token = await self.token_encryption.get_decrypted_access_token(
                token
            )
            async with httpx.AsyncClient() as client:
                await client.post(
                    GOOGLE_REVOKE_URL,
                    params={"token": access_token},
                )
        except Exception:
            logger.warning("Failed to revoke Google token (best effort)")

        return await self.token_repo.delete_by_id(connection_id, user_id)
