"""Delivery checker: determines when message groups are ready for digest delivery.

Stage 3.5 of the agent-driven triage pipeline. No LLM calls.
"""

import logging
from datetime import UTC, datetime

from sqlalchemy import distinct, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.triage import TriageClassification

logger = logging.getLogger(__name__)


class DeliveryChecker:
    """Checks if message groups are ready for delivery based on settle/TTL logic."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_users_with_queued_p1(self) -> list[str]:
        """Get user IDs with queued P1 messages (action=summarize_next, queued=True, deliver_by set)."""
        result = await self.db.execute(
            select(distinct(TriageClassification.user_id))
            .where(TriageClassification.action == "summarize_next")
            .where(TriageClassification.queued_for_digest == True)  # noqa: E712
            .where(TriageClassification.deliver_by.isnot(None))
        )
        return list(result.scalars().all())

    async def get_ready_p1_groups(self, user_id: str) -> list[dict]:
        """Get P1 message groups that are ready for delivery.

        Returns list of dicts: [{"group_id": str, "message_ids": [str], "reason": "settled"|"expired"}]
        """
        now = datetime.now(UTC)

        result = await self.db.execute(
            select(TriageClassification)
            .where(TriageClassification.user_id == user_id)
            .where(TriageClassification.action == "summarize_next")
            .where(TriageClassification.queued_for_digest == True)  # noqa: E712
            .where(TriageClassification.deliver_by.isnot(None))
            .order_by(TriageClassification.created_at.asc())
        )
        items = list(result.scalars().all())

        if not items:
            return []

        # Group by group_id (NULL = standalone group of 1)
        groups: dict[str, list] = {}
        for item in items:
            key = item.group_id or str(item.id)
            if key not in groups:
                groups[key] = []
            groups[key].append(item)

        ready_groups = []
        for group_key, group_items in groups.items():
            last_activity = max(
                (i.last_related_activity_at for i in group_items if i.last_related_activity_at),
                default=None,
            )
            settled_threshold = min(
                (i.settled_threshold for i in group_items if i.settled_threshold),
                default=30,
            )
            earliest_deadline = min(
                (i.deliver_by for i in group_items if i.deliver_by),
                default=now,
            )

            settled = False
            if last_activity:
                minutes_since_activity = (now - last_activity).total_seconds() / 60
                settled = minutes_since_activity >= settled_threshold

            expired = now >= earliest_deadline

            if settled or expired:
                ready_groups.append({
                    "group_id": group_key,
                    "message_ids": [str(i.id) for i in group_items],
                    "reason": "settled" if settled else "expired",
                })

        return ready_groups

    async def get_queued_p2_messages(self, user_id: str) -> list[TriageClassification]:
        """Get all P2 messages queued for EOD digest."""
        result = await self.db.execute(
            select(TriageClassification)
            .where(TriageClassification.user_id == user_id)
            .where(TriageClassification.action == "summarize_eod")
            .where(TriageClassification.queued_for_digest == True)  # noqa: E712
            .where(TriageClassification.is_consolidated == False)  # noqa: E712
            .order_by(TriageClassification.created_at.asc())
        )
        return list(result.scalars().all())

    async def count_p3_messages(self, user_id: str) -> int:
        """Count P3 (ignored) messages for EOD footer."""
        result = await self.db.execute(
            select(func.count())
            .select_from(TriageClassification)
            .where(TriageClassification.user_id == user_id)
            .where(TriageClassification.action == "ignore")
            .where(TriageClassification.queued_for_digest == False)  # noqa: E712
            .where(TriageClassification.reviewed_at.is_(None))
        )
        return result.scalar() or 0

    def is_eod_time(self, eod_review_time: str, current_time_str: str) -> bool:
        """Check if current time matches user's EOD review time (HH:MM format)."""
        return eod_review_time == current_time_str
