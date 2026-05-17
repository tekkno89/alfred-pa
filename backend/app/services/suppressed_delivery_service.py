"""Service for tracking and reviewing suppressed deliveries.

R8: When R2b suppresses a delivery, record it for counterfactual review.
Auto-promote to next digest; surface in EOD review.
"""

import logging
from datetime import datetime, timedelta

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.triage import SuppressedDelivery

logger = logging.getLogger(__name__)

CANONICAL_CAP = 10  # Max suppressed items per user per day
RETENTION_DAYS = 90


class SuppressedDeliveryService:
    """Manages suppressed delivery records for counterfactual review."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def record_suppression(
        self,
        user_id: str,
        message_id: str,
        original_action: str,
        suppression_reason: str,
        outcome_summary: str | None = None,
    ) -> SuppressedDelivery | None:
        """Record a suppressed delivery.

        Respects canonical cap of 10 per user per day.

        Returns:
            SuppressedDelivery if recorded, None if cap reached.
        """
        # Check cap
        today_start = datetime.utcnow().replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        result = await self.db.execute(
            select(func.count()).where(
                SuppressedDelivery.user_id == user_id,
                SuppressedDelivery.created_at >= today_start,
            )
        )
        count = result.scalar() or 0

        if count >= CANONICAL_CAP:
            logger.info(
                f"Suppressed delivery cap reached for user {user_id} "
                f"({count} items today)"
            )
            return None

        suppressed = SuppressedDelivery(
            user_id=user_id,
            message_id=message_id,
            original_action=original_action,
            suppression_reason=suppression_reason,
            outcome_summary=outcome_summary,
        )
        self.db.add(suppressed)
        await self.db.commit()
        await self.db.refresh(suppressed)

        return suppressed

    async def get_for_review(
        self,
        user_id: str,
        limit: int = CANONICAL_CAP,
    ) -> list[SuppressedDelivery]:
        """Get suppressed deliveries for counterfactual review.

        Returns newest items first, up to cap limit.
        """
        result = await self.db.execute(
            select(SuppressedDelivery)
            .where(SuppressedDelivery.user_id == user_id)
            .where(SuppressedDelivery.user_review_response.is_(None))
            .order_by(SuppressedDelivery.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def record_review_response(
        self,
        suppressed_id: str,
        user_id: str,
        response: str,  # "yes" | "no" | "maybe"
    ) -> bool:
        """Record user's review response.

        "yes" responses feed R3 as strong positive signal.
        """
        result = await self.db.execute(
            select(SuppressedDelivery).where(
                SuppressedDelivery.id == suppressed_id,
                SuppressedDelivery.user_id == user_id,
            )
        )
        suppressed = result.scalar_one_or_none()

        if not suppressed:
            return False

        suppressed.user_review_response = response
        await self.db.commit()

        # TODO: If response == "yes", feed to R3 learning consumers

        return True

    async def cleanup_expired(self) -> int:
        """Delete records older than retention period."""
        cutoff = datetime.utcnow() - timedelta(days=RETENTION_DAYS)
        result = await self.db.execute(
            delete(SuppressedDelivery).where(
                SuppressedDelivery.created_at < cutoff
            )
        )
        await self.db.commit()
        return result.rowcount  # type: ignore[attr-defined, no-any-return]
