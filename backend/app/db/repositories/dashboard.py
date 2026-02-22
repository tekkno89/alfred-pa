"""Repositories for dashboard preferences and feature access."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.dashboard import UserDashboardPreference, UserFeatureAccess
from app.db.repositories.base import BaseRepository


class DashboardPreferenceRepository(BaseRepository[UserDashboardPreference]):
    """Repository for user dashboard preference operations."""

    def __init__(self, db: AsyncSession):
        super().__init__(UserDashboardPreference, db)

    async def get_by_user(self, user_id: str) -> list[UserDashboardPreference]:
        """Get all dashboard preferences for a user, ordered by sort_order."""
        result = await self.db.execute(
            select(UserDashboardPreference)
            .where(UserDashboardPreference.user_id == user_id)
            .order_by(UserDashboardPreference.sort_order)
        )
        return list(result.scalars().all())

    async def get_by_user_and_card(
        self, user_id: str, card_type: str
    ) -> UserDashboardPreference | None:
        """Get a specific card preference for a user."""
        result = await self.db.execute(
            select(UserDashboardPreference)
            .where(UserDashboardPreference.user_id == user_id)
            .where(UserDashboardPreference.card_type == card_type)
        )
        return result.scalar_one_or_none()

    async def upsert(
        self,
        user_id: str,
        card_type: str,
        preferences: dict,
        sort_order: int = 0,
    ) -> UserDashboardPreference:
        """Create or update a card preference."""
        existing = await self.get_by_user_and_card(user_id, card_type)
        if existing:
            return await self.update(
                existing, preferences=preferences, sort_order=sort_order
            )
        pref = UserDashboardPreference(
            user_id=user_id,
            card_type=card_type,
            preferences=preferences,
            sort_order=sort_order,
        )
        return await self.create(pref)

    async def delete_by_user_and_card(self, user_id: str, card_type: str) -> bool:
        """Delete a card preference. Returns True if deleted, False if not found."""
        existing = await self.get_by_user_and_card(user_id, card_type)
        if existing:
            await self.delete(existing)
            return True
        return False


class FeatureAccessRepository(BaseRepository[UserFeatureAccess]):
    """Repository for user feature access operations."""

    def __init__(self, db: AsyncSession):
        super().__init__(UserFeatureAccess, db)

    async def is_enabled(self, user_id: str, feature_key: str) -> bool:
        """Check if a feature is enabled for a user. Default-disabled (no row = False)."""
        result = await self.db.execute(
            select(UserFeatureAccess)
            .where(UserFeatureAccess.user_id == user_id)
            .where(UserFeatureAccess.feature_key == feature_key)
        )
        access = result.scalar_one_or_none()
        if access is None:
            return False
        return access.enabled

    async def set_access(
        self,
        user_id: str,
        feature_key: str,
        enabled: bool,
        granted_by: str | None = None,
    ) -> UserFeatureAccess:
        """Set feature access for a user (upsert)."""
        result = await self.db.execute(
            select(UserFeatureAccess)
            .where(UserFeatureAccess.user_id == user_id)
            .where(UserFeatureAccess.feature_key == feature_key)
        )
        existing = result.scalar_one_or_none()
        if existing:
            return await self.update(
                existing, enabled=enabled, granted_by=granted_by
            )
        access = UserFeatureAccess(
            user_id=user_id,
            feature_key=feature_key,
            enabled=enabled,
            granted_by=granted_by,
        )
        return await self.create(access)

    async def get_all_for_user(self, user_id: str) -> list[UserFeatureAccess]:
        """Get all feature access entries for a user."""
        result = await self.db.execute(
            select(UserFeatureAccess)
            .where(UserFeatureAccess.user_id == user_id)
        )
        return list(result.scalars().all())

    async def get_all_for_feature(self, feature_key: str) -> list[UserFeatureAccess]:
        """Get all users with access to a feature (for admin listing)."""
        result = await self.db.execute(
            select(UserFeatureAccess)
            .where(UserFeatureAccess.feature_key == feature_key)
        )
        return list(result.scalars().all())

    async def delete_access(self, user_id: str, feature_key: str) -> bool:
        """Remove feature access override. Returns True if deleted."""
        result = await self.db.execute(
            select(UserFeatureAccess)
            .where(UserFeatureAccess.user_id == user_id)
            .where(UserFeatureAccess.feature_key == feature_key)
        )
        existing = result.scalar_one_or_none()
        if existing:
            await self.delete(existing)
            return True
        return False
