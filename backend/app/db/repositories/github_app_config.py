"""Repository for GitHub App configuration operations."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.github_app_config import GitHubAppConfig
from app.db.repositories.base import BaseRepository


class GitHubAppConfigRepository(BaseRepository[GitHubAppConfig]):
    """Repository for GitHubAppConfig CRUD operations."""

    def __init__(self, db: AsyncSession):
        super().__init__(GitHubAppConfig, db)

    async def get_all_by_user(self, user_id: str) -> list[GitHubAppConfig]:
        """Get all GitHub App configs for a user."""
        result = await self.db.execute(
            select(GitHubAppConfig)
            .where(GitHubAppConfig.user_id == user_id)
            .order_by(GitHubAppConfig.created_at)
        )
        return list(result.scalars().all())

    async def get_by_user_and_label(
        self, user_id: str, label: str
    ) -> GitHubAppConfig | None:
        """Get a GitHub App config by user and label."""
        result = await self.db.execute(
            select(GitHubAppConfig)
            .where(GitHubAppConfig.user_id == user_id)
            .where(GitHubAppConfig.label == label)
        )
        return result.scalar_one_or_none()

    async def create_config(
        self,
        user_id: str,
        label: str,
        client_id: str,
        encrypted_client_secret: str,
        encryption_key_id: str,
        github_app_id: str | None = None,
    ) -> GitHubAppConfig:
        """Create a new GitHub App config."""
        config = GitHubAppConfig(
            user_id=user_id,
            label=label,
            client_id=client_id,
            encrypted_client_secret=encrypted_client_secret,
            encryption_key_id=encryption_key_id,
            github_app_id=github_app_id,
        )
        return await self.create(config)

    async def delete_by_id(self, config_id: str, user_id: str) -> bool:
        """Delete a GitHub App config by ID with ownership check."""
        config = await self.get(config_id)
        if config and config.user_id == user_id:
            await self.delete(config)
            return True
        return False
