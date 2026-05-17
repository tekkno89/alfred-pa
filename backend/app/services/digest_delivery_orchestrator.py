"""Digest delivery orchestrator with pluggable triggers.

Replaces simple digest_scheduler with smarter delivery logic:
- Calendar integration: deliver when meeting ends
- Idle detection: deliver when user is away (placeholder)
- Stale queue: deliver when items get too old
- Focus mode: suppress non-escalation deliveries during focus
"""

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.redis import get_redis
from app.db.models.triage import TriageClassification
from app.db.repositories.triage import (
    TriageClassificationRepository,
    TriageUserSettingsRepository,
)
from app.services.focus import FocusModeService
from app.services.google_calendar import GoogleCalendarService

logger = logging.getLogger(__name__)

STALE_QUEUE_THRESHOLD_MINUTES = 30


@dataclass
class DeliveryTrigger:
    """A trigger that may cause a digest to be delivered."""

    trigger_type: str
    user_id: str
    triggered_at: datetime
    metadata: dict[str, Any] = field(default_factory=dict)


class DeliveryTriggerPlugin(ABC):
    """Abstract base class for delivery trigger plugins."""

    @abstractmethod
    async def check(self, user_id: str, db: AsyncSession) -> DeliveryTrigger | None:
        """Check if trigger condition is met.

        Returns:
            DeliveryTrigger if triggered, None otherwise
        """
        pass

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable name for logging."""
        pass


class CalendarEndTrigger(DeliveryTriggerPlugin):
    """Trigger when calendar event ends with no immediate next event.

    Uses Google Calendar API to check for recently ended events.
    """

    def __init__(self, gap_minutes: int = 5):
        self.gap_minutes = gap_minutes

    @property
    def name(self) -> str:
        return "calendar_end"

    async def check(self, user_id: str, db: AsyncSession) -> DeliveryTrigger | None:
        """Check if user's calendar event just ended with free time after."""
        try:
            cal_service = GoogleCalendarService(db)
            access_token = await cal_service.get_valid_token(user_id)
            if not access_token:
                return None

            now = datetime.now(UTC)
            time_min = (now - timedelta(minutes=5)).isoformat()
            time_max = (now + timedelta(minutes=self.gap_minutes + 5)).isoformat()

            calendars = await cal_service.list_calendars(user_id)
            primary_cal = next((c for c in calendars if c.get("primary")), None)
            if not primary_cal:
                return None

            events = await cal_service.list_events(
                user_id,
                "default",
                primary_cal["id"],
                time_min,
                time_max,
            )

            for event in events:
                if event.get("all_day"):
                    continue

                end_str = event.get("end", "")
                if not end_str:
                    continue

                try:
                    end_time = datetime.fromisoformat(end_str.replace("Z", "+00:00"))
                except ValueError:
                    continue

                if end_time.tzinfo is None:
                    end_time = end_time.replace(tzinfo=UTC)

                time_since_end = (now - end_time).total_seconds() / 60

                if 0 <= time_since_end <= 2:
                    next_event = self._find_next_event(events, end_time)
                    if not next_event:
                        return DeliveryTrigger(
                            trigger_type="calendar_end",
                            user_id=user_id,
                            triggered_at=now,
                            metadata={
                                "event_title": event.get("title", "Unknown"),
                                "event_end": end_str,
                                "gap_minutes": self.gap_minutes,
                            },
                        )

            return None

        except Exception:
            logger.exception(f"CalendarEndTrigger error for user {user_id}")
            return None

    def _find_next_event(
        self, events: list[dict], after_time: datetime
    ) -> dict | None:
        """Find the next event starting after a given time."""
        for event in events:
            if event.get("all_day"):
                continue
            start_str = event.get("start", "")
            if not start_str:
                continue
            try:
                start_time = datetime.fromisoformat(start_str.replace("Z", "+00:00"))
                if start_time.tzinfo is None:
                    start_time = start_time.replace(tzinfo=UTC)
                if start_time > after_time:
                    return event
            except ValueError:
                continue
        return None


class IdleTrigger(DeliveryTriggerPlugin):
    """Placeholder for Slack presence detection.

    Will trigger delivery when user is away/idle.
    Phase 3: Not yet implemented - returns None.
    """

    @property
    def name(self) -> str:
        return "idle_detection"

    async def check(self, user_id: str, db: AsyncSession) -> DeliveryTrigger | None:
        """Check if user is idle (placeholder)."""
        return None


class StaleQueueTrigger(DeliveryTriggerPlugin):
    """Trigger when summarize_next items are older than threshold.

    Ensures items don't sit indefinitely even if other triggers don't fire.
    """

    def __init__(self, stale_threshold_minutes: int = STALE_QUEUE_THRESHOLD_MINUTES):
        self.stale_threshold_minutes = stale_threshold_minutes

    @property
    def name(self) -> str:
        return "stale_queue"

    async def check(self, user_id: str, db: AsyncSession) -> DeliveryTrigger | None:
        """Check if summarize_next items are older than threshold."""
        try:
            cutoff = datetime.utcnow() - timedelta(minutes=self.stale_threshold_minutes)

            result = await db.execute(
                select(TriageClassification)
                .where(TriageClassification.user_id == user_id)
                .where(TriageClassification.action == "summarize_next")
                .where(TriageClassification.queued_for_digest.is_(True))
                .where(TriageClassification.created_at < cutoff)
                .order_by(TriageClassification.created_at.asc())
                .limit(1)
            )
            stale_item = result.scalar_one_or_none()

            if stale_item:
                return DeliveryTrigger(
                    trigger_type="stale_queue",
                    user_id=user_id,
                    triggered_at=datetime.utcnow(),
                    metadata={
                        "oldest_item_age_minutes": int(
                            (datetime.utcnow() - stale_item.created_at).total_seconds() / 60
                        ),
                        "stale_threshold_minutes": self.stale_threshold_minutes,
                    },
                )

            return None

        except Exception:
            logger.exception(f"StaleQueueTrigger error for user {user_id}")
            return None


class DigestDeliveryOrchestrator:
    """Orchestrates digest delivery with pluggable triggers.

    Coordinates multiple trigger plugins to determine when to deliver
    summarize_next items to users.
    """

    def __init__(
        self,
        db: AsyncSession,
        triggers: list[DeliveryTriggerPlugin] | None = None,
    ):
        self.db = db
        self.class_repo = TriageClassificationRepository(db)
        self.settings_repo = TriageUserSettingsRepository(db)
        self.focus_service = FocusModeService(db)

        self.triggers = triggers or [
            CalendarEndTrigger(),
            IdleTrigger(),
            StaleQueueTrigger(),
        ]

    async def check_triggers(self, user_id: str) -> DeliveryTrigger | None:
        """Check all triggers for a user.

        Returns first trigger that fires, or None.
        """
        for trigger in self.triggers:
            try:
                result = await trigger.check(user_id, self.db)
                if result:
                    logger.info(
                        f"Trigger '{trigger.name}' fired for user {user_id}: "
                        f"{result.metadata}"
                    )
                    return result
            except Exception:
                logger.exception(
                    f"Error checking trigger '{trigger.name}' for user {user_id}"
                )

        return None

    async def deliver_summarize_next(
        self,
        user_id: str,
        trigger: DeliveryTrigger,
    ) -> dict[str, Any]:
        """Deliver summarize_next items for a user.

        Respects focus mode - will not deliver during focus unless escalation.

        Returns:
            Dict with delivery status and item count
        """
        in_focus = await self.focus_service.is_in_focus_mode(user_id)

        if in_focus:
            logger.info(
                f"Skipping summarize_next delivery for user {user_id} "
                f"(in focus mode, trigger={trigger.trigger_type})"
            )
            return {
                "status": "skipped_focus_mode",
                "user_id": user_id,
                "trigger": trigger.trigger_type,
            }

        redis = await get_redis()
        dedup_key = f"digest:delivered:{user_id}:{trigger.trigger_type}"
        if await redis.exists(dedup_key):
            logger.debug(
                f"Skipping duplicate delivery for user {user_id} "
                f"(trigger={trigger.trigger_type})"
            )
            return {
                "status": "skipped_dedup",
                "user_id": user_id,
                "trigger": trigger.trigger_type,
            }

        result = await self.db.execute(
            select(TriageClassification)
            .where(TriageClassification.user_id == user_id)
            .where(TriageClassification.action == "summarize_next")
            .where(TriageClassification.queued_for_digest.is_(True))
            .where(TriageClassification.focus_session_id.is_(None))
            .order_by(TriageClassification.created_at.asc())
        )
        items = list(result.scalars().all())

        if not items:
            return {
                "status": "no_items",
                "user_id": user_id,
                "trigger": trigger.trigger_type,
            }

        from app.worker.scheduler import get_redis_pool

        pool = await get_redis_pool()
        job_id = f"digest_summarize_next_{user_id}_{datetime.utcnow().strftime('%Y%m%d_%H%M')}"
        await pool.enqueue_job(
            "send_digest",
            user_id=user_id,
            priority="summarize_next",
            digest_type=trigger.trigger_type,
            _job_id=job_id,
        )

        await redis.set(dedup_key, "1", ex=300)

        logger.info(
            f"Enqueued summarize_next digest for user {user_id}: "
            f"{len(items)} items (trigger={trigger.trigger_type})"
        )

        return {
            "status": "enqueued",
            "user_id": user_id,
            "trigger": trigger.trigger_type,
            "item_count": len(items),
        }

    async def deliver_eod_digest(self, user_id: str) -> dict[str, Any]:
        """Deliver end-of-day digest for a user.

        Called at the user's configured EOD review time.
        Respects focus mode.

        Returns:
            Dict with delivery status
        """
        settings = await self.settings_repo.get_by_user_id(user_id)
        if not settings or not settings.is_always_on:
            return {"status": "skipped_not_enabled", "user_id": user_id}

        in_focus = await self.focus_service.is_in_focus_mode(user_id)
        if in_focus:
            logger.info(
                f"Skipping EOD digest for user {user_id} (in focus mode)"
            )
            return {"status": "skipped_focus_mode", "user_id": user_id}

        redis = await get_redis()
        dedup_key = f"digest:eod:{user_id}:{datetime.utcnow().strftime('%Y%m%d')}"
        if await redis.exists(dedup_key):
            logger.debug(f"Skipping duplicate EOD digest for user {user_id}")
            return {"status": "skipped_dedup", "user_id": user_id}

        result = await self.db.execute(
            select(TriageClassification)
            .where(TriageClassification.user_id == user_id)
            .where(
                TriageClassification.action.in_(["summarize_next", "summarize_eod"])
            )
            .where(TriageClassification.queued_for_digest.is_(True))
            .where(TriageClassification.focus_session_id.is_(None))
        )
        items = list(result.scalars().all())

        if not items:
            return {"status": "no_items", "user_id": user_id}

        from app.worker.scheduler import get_redis_pool

        pool = await get_redis_pool()
        job_id = f"digest_eod_{user_id}_{datetime.utcnow().strftime('%Y%m%d_%H%M')}"
        await pool.enqueue_job(
            "send_digest",
            user_id=user_id,
            priority="all",
            digest_type="end_of_day",
            _job_id=job_id,
        )

        await redis.set(dedup_key, "1", ex=86400)

        logger.info(
            f"Enqueued EOD digest for user {user_id}: {len(items)} items"
        )

        return {
            "status": "enqueued",
            "user_id": user_id,
            "item_count": len(items),
        }

    async def get_users_with_pending_items(self) -> list[str]:
        """Get user IDs that have pending summarize_next items."""
        result = await self.db.execute(
            select(TriageClassification.user_id)
            .where(TriageClassification.action == "summarize_next")
            .where(TriageClassification.queued_for_digest.is_(True))
            .where(TriageClassification.focus_session_id.is_(None))
            .distinct()
        )
        return list(result.scalars().all())
