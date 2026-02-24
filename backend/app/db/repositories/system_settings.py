"""System settings repository."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.system_settings import SystemSetting


class SystemSettingsRepository:
    """Repository for system-wide settings."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get(self, key: str) -> str | None:
        """Get a setting value by key."""
        result = await self.db.execute(
            select(SystemSetting.value).where(SystemSetting.key == key)
        )
        return result.scalar_one_or_none()

    async def get_bool(self, key: str, default: bool = True) -> bool:
        """Get a boolean setting. Returns default if not found."""
        value = await self.get(key)
        if value is None:
            return default
        return value.lower() == "true"

    async def set(self, key: str, value: str) -> SystemSetting:
        """Set a setting value, creating or updating as needed."""
        result = await self.db.execute(
            select(SystemSetting).where(SystemSetting.key == key)
        )
        setting = result.scalar_one_or_none()
        if setting:
            setting.value = value
        else:
            setting = SystemSetting(key=key, value=value)
            self.db.add(setting)
        await self.db.flush()
        await self.db.refresh(setting)
        return setting

    async def get_all(self) -> list[SystemSetting]:
        """Get all settings."""
        result = await self.db.execute(
            select(SystemSetting).order_by(SystemSetting.key)
        )
        return list(result.scalars().all())
