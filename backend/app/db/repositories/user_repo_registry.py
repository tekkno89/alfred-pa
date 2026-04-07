from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.user_repository import UserRepo
from app.db.repositories.base import BaseRepository


class RepoRegistryRepository(BaseRepository[UserRepo]):
    """Repository for user-registered repositories."""

    def __init__(self, db: AsyncSession):
        super().__init__(UserRepo, db)

    async def get_all_by_user(self, user_id: str) -> list[UserRepo]:
        result = await self.db.execute(
            select(UserRepo)
            .where(UserRepo.user_id == user_id)
            .order_by(UserRepo.owner, UserRepo.repo_name)
        )
        return list(result.scalars().all())

    async def get_by_id_and_user(self, id: str, user_id: str) -> UserRepo | None:
        result = await self.db.execute(
            select(UserRepo)
            .where(UserRepo.id == id, UserRepo.user_id == user_id)
        )
        return result.scalar_one_or_none()

    async def resolve(self, user_id: str, input_name: str) -> UserRepo | list[UserRepo]:
        """Resolve a short repo name or alias to a UserRepo.

        Returns a single UserRepo on unambiguous match, or a list
        (empty = not found, >1 = ambiguous).
        """
        # 1. Try alias match (exact, case-insensitive)
        result = await self.db.execute(
            select(UserRepo)
            .where(
                UserRepo.user_id == user_id,
                UserRepo.alias.ilike(input_name),
            )
        )
        alias_match = result.scalar_one_or_none()
        if alias_match:
            return alias_match

        # 2. Try repo_name match (exact, case-insensitive)
        result = await self.db.execute(
            select(UserRepo)
            .where(
                UserRepo.user_id == user_id,
                UserRepo.repo_name.ilike(input_name),
            )
        )
        matches = list(result.scalars().all())
        if len(matches) == 1:
            return matches[0]
        return matches  # empty or ambiguous

    async def check_alias_conflict(
        self, user_id: str, alias: str, exclude_id: str | None = None
    ) -> bool:
        """Check if an alias is already used by this user."""
        query = select(UserRepo).where(
            UserRepo.user_id == user_id,
            UserRepo.alias.ilike(alias),
        )
        if exclude_id:
            query = query.where(UserRepo.id != exclude_id)
        result = await self.db.execute(query)
        return result.scalar_one_or_none() is not None

    async def delete_by_id_and_user(self, id: str, user_id: str) -> bool:
        entry = await self.get_by_id_and_user(id, user_id)
        if entry:
            await self.delete(entry)
            return True
        return False
