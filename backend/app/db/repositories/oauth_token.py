"""Repository for OAuth token operations."""

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import UserOAuthToken
from app.db.repositories.base import BaseRepository


class OAuthTokenRepository(BaseRepository[UserOAuthToken]):
    """Repository for UserOAuthToken CRUD operations."""

    def __init__(self, db: AsyncSession):
        super().__init__(UserOAuthToken, db)

    async def get_by_user_and_provider(
        self, user_id: str, provider: str
    ) -> UserOAuthToken | None:
        """Get OAuth token for a user and provider (default label)."""
        result = await self.db.execute(
            select(UserOAuthToken)
            .where(UserOAuthToken.user_id == user_id)
            .where(UserOAuthToken.provider == provider)
            .where(UserOAuthToken.account_label == "default")
        )
        return result.scalar_one_or_none()

    async def get_by_user_provider_and_label(
        self, user_id: str, provider: str, account_label: str
    ) -> UserOAuthToken | None:
        """Get OAuth token for a user, provider, and account label."""
        result = await self.db.execute(
            select(UserOAuthToken)
            .where(UserOAuthToken.user_id == user_id)
            .where(UserOAuthToken.provider == provider)
            .where(UserOAuthToken.account_label == account_label)
        )
        return result.scalar_one_or_none()

    async def get_all_by_user_and_provider(
        self, user_id: str, provider: str
    ) -> list[UserOAuthToken]:
        """Get all OAuth tokens for a user and provider (all labels)."""
        result = await self.db.execute(
            select(UserOAuthToken)
            .where(UserOAuthToken.user_id == user_id)
            .where(UserOAuthToken.provider == provider)
            .order_by(UserOAuthToken.created_at)
        )
        return list(result.scalars().all())

    async def upsert(
        self,
        user_id: str,
        provider: str,
        access_token: str,
        refresh_token: str | None = None,
        scope: str | None = None,
        expires_at: datetime | None = None,
        account_label: str = "default",
        encrypted_access_token: str | None = None,
        encrypted_refresh_token: str | None = None,
        encryption_key_id: str | None = None,
        external_account_id: str | None = None,
        token_type: str = "oauth",
        github_app_config_id: str | None = None,
    ) -> UserOAuthToken:
        """Create or update OAuth token for a user, provider, and label."""
        token = await self.get_by_user_provider_and_label(
            user_id, provider, account_label
        )
        if token:
            return await self.update(
                token,
                access_token=access_token,
                refresh_token=refresh_token,
                scope=scope,
                expires_at=expires_at,
                encrypted_access_token=encrypted_access_token,
                encrypted_refresh_token=encrypted_refresh_token,
                encryption_key_id=encryption_key_id,
                external_account_id=external_account_id,
                token_type=token_type,
                github_app_config_id=github_app_config_id,
            )
        else:
            token = UserOAuthToken(
                user_id=user_id,
                provider=provider,
                access_token=access_token,
                refresh_token=refresh_token,
                scope=scope,
                expires_at=expires_at,
                account_label=account_label,
                encrypted_access_token=encrypted_access_token,
                encrypted_refresh_token=encrypted_refresh_token,
                encryption_key_id=encryption_key_id,
                external_account_id=external_account_id,
                token_type=token_type,
                github_app_config_id=github_app_config_id,
            )
            return await self.create(token)

    async def delete_by_user_and_provider(self, user_id: str, provider: str) -> bool:
        """Delete OAuth token for a user and provider (default label). Returns True if deleted."""
        token = await self.get_by_user_and_provider(user_id, provider)
        if token:
            await self.delete(token)
            return True
        return False

    async def delete_by_id(self, token_id: str, user_id: str) -> bool:
        """Delete OAuth token by ID with ownership check. Returns True if deleted."""
        token = await self.get(token_id)
        if token and token.user_id == user_id:
            await self.delete(token)
            return True
        return False
