"""Active hours service for triage delivery scheduling."""

from datetime import datetime
from uuid import UUID
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.triage import ActiveHoursConfig, TriageUserSettings


class ActiveHoursService:
    """Service for managing and checking active hours configuration."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_user_configs(self, user_id: UUID | str) -> list[ActiveHoursConfig]:
        """Get all active hours configs for a user."""
        result = await self.db.execute(
            select(ActiveHoursConfig)
            .where(ActiveHoursConfig.user_id == user_id)
            .order_by(ActiveHoursConfig.day_of_week)
        )
        return list(result.scalars().all())

    async def is_within_active_hours(
        self,
        user_id: UUID | str,
        now: datetime | None = None,
    ) -> bool:
        """
        Check if current time is within user's active hours.
        
        Returns True if:
        - No config exists (24/7 mode)
        - Current day is disabled
        - Current time is within configured window
        """
        configs = await self.get_user_configs(user_id)
        
        # No config = always active
        if not configs:
            return True

        now = now or datetime.utcnow()
        day_of_week = now.weekday()  # 0=Monday, 6=Sunday
        current_time = now.strftime("%H:%M")

        # Find config for today
        day_config = next(
            (c for c in configs if c.day_of_week == day_of_week),
            None,
        )

        # No config for today = always active
        if not day_config:
            return True

        # Disabled day = always active
        if not day_config.is_enabled:
            return True

        # Check if within window
        return day_config.start_time <= current_time <= day_config.end_time

    async def should_deliver_now(
        self,
        user_id: UUID | str,
        action: str,
        now: datetime | None = None,
    ) -> bool:
        """
        Determine if a message should be delivered now or queued.
        
        Args:
            user_id: User UUID
            action: Classification action (notify_now, summarize_next, etc.)
            now: Current datetime (for testing)
            
        Returns:
            True if should deliver immediately, False if should queue
        """
        # Check if within active hours
        is_active = await self.is_within_active_hours(user_id, now)
        
        if is_active:
            return True

        # Outside active hours - check breakthrough setting
        result = await self.db.execute(
            select(TriageUserSettings).where(TriageUserSettings.user_id == user_id)
        )
        settings = result.scalars().first()

        # No settings = allow_notify_now (default)
        breakthrough = settings.active_hours_breakthrough if settings else "allow_notify_now"

        if breakthrough == "queue_all":
            return False

        # allow_notify_now: only P0 breaks through
        return action == "notify_now"

    async def set_configs(
        self,
        user_id: UUID | str,
        configs: list[dict],
    ) -> list[ActiveHoursConfig]:
        """
        Set active hours configs for a user (replaces existing).
        
        Args:
            user_id: User UUID
            configs: List of {day_of_week, start_time, end_time, is_enabled}
            
        Returns:
            List of created/updated configs
        """
        # Delete existing configs
        existing = await self.get_user_configs(user_id)
        for config in existing:
            await self.db.delete(config)

        # Create new configs
        new_configs = []
        for config_data in configs:
            config = ActiveHoursConfig(
                user_id=user_id,
                day_of_week=config_data["day_of_week"],
                start_time=config_data["start_time"],
                end_time=config_data["end_time"],
                is_enabled=config_data.get("is_enabled", True),
            )
            self.db.add(config)
            new_configs.append(config)

        await self.db.commit()
        return new_configs

    async def set_breakthrough(
        self,
        user_id: UUID | str,
        breakthrough: str,
    ) -> TriageUserSettings:
        """Set the breakthrough behavior for outside active hours."""
        result = await self.db.execute(
            select(TriageUserSettings).where(TriageUserSettings.user_id == user_id)
        )
        settings = result.scalars().first()

        if not settings:
            settings = TriageUserSettings(user_id=user_id)
            self.db.add(settings)

        settings.active_hours_breakthrough = breakthrough
        await self.db.commit()
        return settings
