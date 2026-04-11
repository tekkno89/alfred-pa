"""Alert deduplication logic for triage notifications."""

import logging
from datetime import datetime, timedelta

from sqlalchemy import func, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.redis import get_redis
from app.db.models.triage import TriageClassification

logger = logging.getLogger(__name__)


class AlertDeduplicationService:
    """Manages alert deduplication using Redis + DB."""

    def __init__(self, db: AsyncSession, redis_client=None):
        self.db = db
        self._redis = redis_client

    async def _get_redis(self):
        """Get Redis client (lazy initialization)."""
        if not self._redis:
            self._redis = await get_redis()
        return self._redis

    async def should_alert(
        self,
        user_id: str,
        classification_id: str,
        thread_ts: str | None,
        sender_slack_id: str,
        dedup_window_minutes: int = 30,
    ) -> bool:
        """
        Check if we should send an alert for this classification.

        Rules:
        - Don't alert if same thread alerted within X minutes
        - Don't alert if same sender alerted within X minutes
        - P0 alerts always check dedup, other priorities skip dedup

        Args:
            user_id: User ID
            classification_id: Classification ID
            thread_ts: Thread timestamp (None for standalone messages)
            sender_slack_id: Sender Slack ID
            dedup_window_minutes: Deduplication window in minutes

        Returns:
            True if alert should be sent, False if should be deduplicated
        """
        redis = await self._get_redis()
        now = datetime.utcnow()

        # Check thread dedup
        if thread_ts:
            thread_key = f"triage:alert:thread:{user_id}:{thread_ts}"
            last_alert = await redis.get(thread_key)
            if last_alert:
                last_time = datetime.fromisoformat(last_alert.decode())
                if now - last_time < timedelta(minutes=dedup_window_minutes):
                    logger.debug(
                        f"Skipping alert: thread {thread_ts} alerted "
                        f"{(now - last_time).seconds}s ago (window: {dedup_window_minutes}min)"
                    )
                    return False

        # Check sender dedup
        sender_key = f"triage:alert:sender:{user_id}:{sender_slack_id}"
        last_alert = await redis.get(sender_key)
        if last_alert:
            last_time = datetime.fromisoformat(last_alert.decode())
            if now - last_time < timedelta(minutes=dedup_window_minutes):
                logger.debug(
                    f"Skipping alert: sender {sender_slack_id} alerted "
                    f"{(now - last_time).seconds}s ago (window: {dedup_window_minutes}min)"
                )
                return False

        # Mark as alerted in Redis
        ttl = dedup_window_minutes * 60 + 300  # Extra 5 min buffer
        now_iso = now.isoformat()

        if thread_ts:
            await redis.set(thread_key, now_iso, ex=ttl)
        await redis.set(sender_key, now_iso, ex=ttl)

        logger.debug(
            f"Alert approved for classification {classification_id} "
            f"(thread={thread_ts}, sender={sender_slack_id})"
        )
        return True

    async def mark_alerted(self, classification_id: str) -> None:
        """
        Update DB record for alert tracking.

        Sets last_alerted_at to now and increments alert_count.

        Args:
            classification_id: Classification ID to update
        """
        await self.db.execute(
            update(TriageClassification)
            .where(TriageClassification.id == classification_id)
            .values(
                last_alerted_at=func.now(),
                alert_count=TriageClassification.alert_count + 1,
                queued_for_digest=False,
            )
        )
        await self.db.flush()
        logger.debug(f"Marked classification {classification_id} as alerted in DB")