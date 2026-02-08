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
        """Get OAuth token for a user and provider."""
        result = await self.db.execute(
            select(UserOAuthToken)
            .where(UserOAuthToken.user_id == user_id)
            .where(UserOAuthToken.provider == provider)
        )
        return result.scalar_one_or_none()

    async def upsert(
        self,
        user_id: str,
        provider: str,
        access_token: str,
        refresh_token: str | None = None,
        scope: str | None = None,
        expires_at: datetime | None = None,
    ) -> UserOAuthToken:
        """Create or update OAuth token for a user and provider."""
        token = await self.get_by_user_and_provider(user_id, provider)
        if token:
            return await self.update(
                token,
                access_token=access_token,
                refresh_token=refresh_token,
                scope=scope,
                expires_at=expires_at,
            )
        else:
            token = UserOAuthToken(
                user_id=user_id,
                provider=provider,
                access_token=access_token,
                refresh_token=refresh_token,
                scope=scope,
                expires_at=expires_at,
            )
            return await self.create(token)

    async def delete_by_user_and_provider(self, user_id: str, provider: str) -> bool:
        """Delete OAuth token for a user and provider. Returns True if deleted."""
        token = await self.get_by_user_and_provider(user_id, provider)
        if token:
            await self.delete(token)
            return True
        return False
