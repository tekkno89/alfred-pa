"""Repository for Focus mode operations."""

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import FocusModeState, FocusSettings, FocusVIPList
from app.db.repositories.base import BaseRepository


class FocusModeStateRepository(BaseRepository[FocusModeState]):
    """Repository for FocusModeState CRUD operations."""

    def __init__(self, db: AsyncSession):
        super().__init__(FocusModeState, db)

    async def get_by_user_id(self, user_id: str) -> FocusModeState | None:
        """Get focus mode state for a user."""
        result = await self.db.execute(
            select(FocusModeState).where(FocusModeState.user_id == user_id)
        )
        return result.scalar_one_or_none()

    async def get_or_create(self, user_id: str) -> FocusModeState:
        """Get existing or create new focus mode state for a user."""
        state = await self.get_by_user_id(user_id)
        if not state:
            state = FocusModeState(user_id=user_id)
            state = await self.create(state)
        return state

    async def get_active_expired(self, before: datetime) -> list[FocusModeState]:
        """Get all active focus sessions that have expired."""
        result = await self.db.execute(
            select(FocusModeState)
            .where(FocusModeState.is_active == True)  # noqa: E712
            .where(FocusModeState.ends_at != None)  # noqa: E711
            .where(FocusModeState.ends_at < before)
        )
        return list(result.scalars().all())


class FocusSettingsRepository(BaseRepository[FocusSettings]):
    """Repository for FocusSettings CRUD operations."""

    def __init__(self, db: AsyncSession):
        super().__init__(FocusSettings, db)

    async def get_by_user_id(self, user_id: str) -> FocusSettings | None:
        """Get focus settings for a user."""
        result = await self.db.execute(
            select(FocusSettings).where(FocusSettings.user_id == user_id)
        )
        return result.scalar_one_or_none()

    async def get_or_create(self, user_id: str) -> FocusSettings:
        """Get existing or create new focus settings for a user."""
        settings = await self.get_by_user_id(user_id)
        if not settings:
            settings = FocusSettings(user_id=user_id)
            settings = await self.create(settings)
        return settings


class FocusVIPListRepository(BaseRepository[FocusVIPList]):
    """Repository for FocusVIPList CRUD operations."""

    def __init__(self, db: AsyncSession):
        super().__init__(FocusVIPList, db)

    async def get_by_user_id(self, user_id: str) -> list[FocusVIPList]:
        """Get all VIP entries for a user."""
        result = await self.db.execute(
            select(FocusVIPList).where(FocusVIPList.user_id == user_id)
        )
        return list(result.scalars().all())

    async def is_vip(self, user_id: str, slack_user_id: str) -> bool:
        """Check if a Slack user is in the VIP list."""
        result = await self.db.execute(
            select(FocusVIPList)
            .where(FocusVIPList.user_id == user_id)
            .where(FocusVIPList.slack_user_id == slack_user_id)
        )
        return result.scalar_one_or_none() is not None

    async def add_vip(
        self, user_id: str, slack_user_id: str, display_name: str | None = None
    ) -> FocusVIPList:
        """Add a VIP user."""
        vip = FocusVIPList(
            user_id=user_id,
            slack_user_id=slack_user_id,
            display_name=display_name,
        )
        return await self.create(vip)

    async def remove_vip(self, user_id: str, slack_user_id: str) -> bool:
        """Remove a VIP user. Returns True if removed, False if not found."""
        result = await self.db.execute(
            select(FocusVIPList)
            .where(FocusVIPList.user_id == user_id)
            .where(FocusVIPList.slack_user_id == slack_user_id)
        )
        vip = result.scalar_one_or_none()
        if vip:
            await self.delete(vip)
            return True
        return False
