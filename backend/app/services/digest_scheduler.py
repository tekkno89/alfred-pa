"""Digest scheduling service for configurable alert cadence."""

import logging
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.redis import get_redis
from app.db.models.triage import TriageUserSettings
from app.db.repositories.triage import (
    TriageClassificationRepository,
    TriageUserSettingsRepository,
)
from app.services.timezone import get_user_timezone, get_current_time_in_tz

logger = logging.getLogger(__name__)


class DigestScheduler:
    """Manages scheduled digest delivery based on user preferences."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.settings_repo = TriageUserSettingsRepository(db)
        self.class_repo = TriageClassificationRepository(db)

    async def schedule_digest_jobs(self) -> None:
        """
        Schedule digest jobs for all users based on their preferences.

        Called by cron job every 5 minutes to check:
        - P1/P2 interval-based digests
        - P1/P2 time-based digests
        - P3 daily digests
        """
        from app.worker.scheduler import get_redis_pool

        pool = await get_redis_pool()

        settings_list = await self.settings_repo.get_all_always_on()

        now = datetime.utcnow()

        logger.info(
            f"DigestScheduler running at {now.isoformat()}, "
            f"checking {len(settings_list)} users"
        )

        for settings in settings_list:
            try:
                await self._schedule_user_digests(settings, now, pool)
            except Exception:
                logger.exception(
                    f"Failed to schedule digests for user {settings.user_id}"
                )

    async def _schedule_user_digests(
        self, settings: TriageUserSettings, now: datetime, pool
    ) -> None:
        """Schedule digests for a single user."""
        user_id = settings.user_id

        user_tz = await get_user_timezone(self.db, user_id)
        now_local = get_current_time_in_tz(user_tz)
        current_time = now_local.strftime("%H:%M")

        logger.debug(f"User {user_id} timezone: {user_tz}, local time: {current_time}")

        from app.services.focus import FocusModeService

        focus_service = FocusModeService(self.db)
        in_focus = await focus_service.is_in_focus_mode(user_id)
        if in_focus:
            logger.debug(
                f"Skipping scheduled digests for user {user_id} (in focus mode)"
            )
            return

        if (
            settings.p1_alerts_enabled
            and settings.p1_digest_times
            and current_time in settings.p1_digest_times
        ):
            logger.info(
                f"Scheduling P1 time-based digest for user {user_id} at {current_time} ({user_tz})"
            )
            await self._enqueue_digest(pool, user_id, "p1", "scheduled")

        if (
            settings.p2_alerts_enabled
            and settings.p2_digest_times
            and current_time in settings.p2_digest_times
        ):
            logger.info(
                f"Scheduling P2 time-based digest for user {user_id} at {current_time} ({user_tz})"
            )
            await self._enqueue_digest(pool, user_id, "p2", "scheduled")

        if (
            settings.p3_alerts_enabled
            and settings.p3_digest_time
            and current_time == settings.p3_digest_time
        ):
            logger.info(
                f"Scheduling P3 daily digest for user {user_id} at {current_time} ({user_tz})"
            )
            await self._enqueue_digest(pool, user_id, "p3", "daily")

        # Interval-based digests (check if next interval elapsed)
        await self._check_interval_digests(settings, user_id, now, user_tz, pool)

    async def _check_interval_digests(
        self,
        settings: TriageUserSettings,
        user_id: str,
        now: datetime,
        user_tz: str,
        pool,
    ) -> None:
        """Check if interval-based digest should be sent."""
        redis = await get_redis()

        if settings.p1_alerts_enabled and settings.p1_digest_interval_minutes:
            await self._check_interval_for_priority(
                redis=redis,
                pool=pool,
                user_id=user_id,
                priority="p1",
                interval_minutes=settings.p1_digest_interval_minutes,
                active_hours_start=settings.p1_digest_active_hours_start,
                active_hours_end=settings.p1_digest_active_hours_end,
                outside_hours_behavior=settings.p1_digest_outside_hours_behavior,
                now=now,
                user_tz=user_tz,
            )

        if settings.p2_alerts_enabled and settings.p2_digest_interval_minutes:
            await self._check_interval_for_priority(
                redis=redis,
                pool=pool,
                user_id=user_id,
                priority="p2",
                interval_minutes=settings.p2_digest_interval_minutes,
                active_hours_start=settings.p2_digest_active_hours_start,
                active_hours_end=settings.p2_digest_active_hours_end,
                outside_hours_behavior=settings.p2_digest_outside_hours_behavior,
                now=now,
                user_tz=user_tz,
            )

    async def _check_interval_for_priority(
        self,
        redis,
        pool,
        user_id: str,
        priority: str,
        interval_minutes: int,
        active_hours_start: str | None,
        active_hours_end: str | None,
        outside_hours_behavior: str | None,
        now: datetime,
        user_tz: str,
    ) -> None:
        """Check if interval-based digest should be sent for a specific priority."""
        now_local = get_current_time_in_tz(user_tz)
        current_time = now_local.strftime("%H:%M")
        is_active = True

        if active_hours_start and active_hours_end:
            is_active = active_hours_start <= current_time < active_hours_end

        key = f"triage:digest:{priority}:{user_id}"

        # If outside active hours
        if not is_active:
            # Check if we should queue summary for next window
            if outside_hours_behavior == "summary_next_window":
                # Queue at start of next active window
                pending_key = f"triage:digest:pending:{priority}:{user_id}"
                has_pending = await redis.get(pending_key)

                if not has_pending:
                    # Check if there are items to summarize
                    count = await self.class_repo.count_unalerted(user_id, priority)
                    if count > 0:
                        # Mark as pending for next window
                        await redis.set(pending_key, "1", ex=86400)  # 24h TTL
                        logger.info(
                            f"Marked pending {priority} digest for user {user_id} "
                            f"at next active window ({active_hours_start})"
                        )
            return

        # In active hours - check interval
        last_digest = await redis.get(key)
        should_send = False

        if not last_digest:
            should_send = True
        else:
            # Handle both bytes and string from Redis
            if isinstance(last_digest, bytes):
                last_digest = last_digest.decode()
            last_time = datetime.fromisoformat(last_digest)
            if self._interval_elapsed(last_time, now, interval_minutes):
                should_send = True

        if should_send:
            # Check if there are items to digest
            count = await self.class_repo.count_unalerted(user_id, priority)
            if count > 0:
                logger.info(
                    f"Scheduling {priority} interval digest for user {user_id} "
                    f"({count} items, interval={interval_minutes}min)"
                )
                await self._enqueue_digest(pool, user_id, priority, "interval")
                await redis.set(key, now.isoformat(), ex=86400)

    def _interval_elapsed(
        self, last_digest: datetime, now: datetime, interval_minutes: int
    ) -> bool:
        """Check if enough time has elapsed since last digest."""
        return (now - last_digest) >= timedelta(minutes=interval_minutes)

    async def _enqueue_digest(
        self, pool, user_id: str, priority: str, digest_type: str
    ) -> None:
        """Enqueue a digest delivery job."""
        job_id = (
            f"digest_{priority}_{user_id}_{datetime.utcnow().strftime('%Y%m%d_%H%M')}"
        )
        try:
            await pool.enqueue_job(
                "send_digest",
                user_id=user_id,
                priority=priority,
                digest_type=digest_type,
                _job_id=job_id,
            )
            logger.info(f"Enqueued digest job: {job_id}")
        except Exception:
            logger.exception(f"Failed to enqueue digest job: {job_id}")
