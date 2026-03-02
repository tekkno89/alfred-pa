"""Token encryption service wrapping encrypt/decrypt for OAuth tokens."""

import logging
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.encryption import get_encryption_service
from app.db.models import UserOAuthToken
from app.db.repositories import EncryptionKeyRepository, OAuthTokenRepository

logger = logging.getLogger(__name__)

DEK_KEY_NAME = "oauth_tokens_dek_v1"


class TokenEncryptionService:
    """Service for storing and retrieving encrypted OAuth tokens."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.token_repo = OAuthTokenRepository(db)
        self.key_repo = EncryptionKeyRepository(db)
        self._encryption = get_encryption_service()

    async def _get_or_create_dek(self) -> tuple[str, bytes]:
        """Get the active DEK, or create one if it doesn't exist.

        Returns (encryption_key_id, encrypted_dek).
        """
        key = await self.key_repo.get_active_by_name(DEK_KEY_NAME)
        if key:
            return key.id, key.encrypted_dek

        # Generate a new DEK
        settings = get_settings()
        encrypted_dek, _ = self._encryption.generate_dek()
        key = await self.key_repo.create_key(
            key_name=DEK_KEY_NAME,
            encrypted_dek=encrypted_dek,
            kek_provider=settings.encryption_kek_provider,
        )
        return key.id, key.encrypted_dek

    async def store_encrypted_token(
        self,
        user_id: str,
        provider: str,
        access_token: str,
        refresh_token: str | None = None,
        scope: str | None = None,
        expires_at: datetime | None = None,
        account_label: str = "default",
        external_account_id: str | None = None,
        token_type: str = "oauth",
        github_app_config_id: str | None = None,
    ) -> UserOAuthToken:
        """Encrypt and store an OAuth token."""
        key_id, encrypted_dek = await self._get_or_create_dek()

        encrypted_access = self._encryption.encrypt(access_token, encrypted_dek)
        encrypted_refresh = None
        if refresh_token:
            encrypted_refresh = self._encryption.encrypt(
                refresh_token, encrypted_dek
            )

        return await self.token_repo.upsert(
            user_id=user_id,
            provider=provider,
            access_token="encrypted",  # placeholder for the non-null column
            refresh_token=None,
            scope=scope,
            expires_at=expires_at,
            account_label=account_label,
            encrypted_access_token=encrypted_access,
            encrypted_refresh_token=encrypted_refresh,
            encryption_key_id=key_id,
            external_account_id=external_account_id,
            token_type=token_type,
            github_app_config_id=github_app_config_id,
        )

    async def get_decrypted_access_token(self, token: UserOAuthToken) -> str:
        """Decrypt and return the access token."""
        if token.encrypted_access_token and token.encryption_key_id:
            key = await self.key_repo.get(token.encryption_key_id)
            if key:
                return self._encryption.decrypt(
                    token.encrypted_access_token, key.encrypted_dek
                )
        # Fallback to plaintext (for tokens not yet migrated)
        return token.access_token

    async def get_decrypted_refresh_token(
        self, token: UserOAuthToken
    ) -> str | None:
        """Decrypt and return the refresh token, if present."""
        if token.encrypted_refresh_token and token.encryption_key_id:
            key = await self.key_repo.get(token.encryption_key_id)
            if key:
                return self._encryption.decrypt(
                    token.encrypted_refresh_token, key.encrypted_dek
                )
        # Fallback to plaintext
        return token.refresh_token
