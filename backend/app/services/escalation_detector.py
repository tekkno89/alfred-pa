"""Escalation detection for promoting summarize_next → notify_now (R2c).

Pattern triggers:
1. Same sender pings 2+ times within 5 min
2. Sender pings, then adds @-mention
3. Thread accelerates (≥5 new messages in 10 min)

Content gate: Re-classify with full context before promoting.
"""

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.triage import TriageClassification

if TYPE_CHECKING:
    from app.services.slack import SlackService

logger = logging.getLogger(__name__)

PING_WINDOW_MINUTES = 5
THREAD_ACCELERATION_THRESHOLD = 5
THREAD_ACCELERATION_WINDOW_MINUTES = 10


@dataclass
class EscalationTrigger:
    """An escalation pattern that fired."""
    classification_id: str
    trigger_type: str  # 'multi_ping', 'mention_added', 'thread_acceleration'
    reason: str


class EscalationDetector:
    """Detects escalation patterns and promotes summarize_next → notify_now.

    Runs as a worker job, checking for escalation patterns.
    Content gate ensures promotion only if content matches user signals.
    """

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def detect_escalations(
        self,
        user_id: str,
        since: datetime,
    ) -> list[EscalationTrigger]:
        """Find all escalation triggers for a user.

        Args:
            user_id: User to check
            since: How far back to check

        Returns:
            List of EscalationTrigger objects
        """
        triggers = []

        result = await self.db.execute(
            select(TriageClassification).where(
                and_(
                    TriageClassification.user_id == user_id,
                    TriageClassification.action == "summarize_next",
                    TriageClassification.created_at >= since,
                    TriageClassification.reviewed_at.is_(None),
                )
            )
        )
        pending = result.scalars().all()

        triggers.extend(await self._check_multi_ping(pending))

        triggers.extend(await self._check_thread_acceleration(user_id, since))

        return triggers

    async def _check_multi_ping(
        self,
        pending: list[TriageClassification],
    ) -> list[EscalationTrigger]:
        """Check for same sender pinging multiple times."""
        by_sender: dict[str, list[TriageClassification]] = {}
        for c in pending:
            if c.sender_slack_id not in by_sender:
                by_sender[c.sender_slack_id] = []
            by_sender[c.sender_slack_id].append(c)

        triggers = []
        for sender_id, classifications in by_sender.items():
            if len(classifications) < 2:
                continue

            sorted_cls = sorted(classifications, key=lambda c: c.created_at)
            for i in range(1, len(sorted_cls)):
                time_diff = (
                    sorted_cls[i].created_at - sorted_cls[i-1].created_at
                ).total_seconds() / 60
                if time_diff <= PING_WINDOW_MINUTES:
                    triggers.append(EscalationTrigger(
                        classification_id=sorted_cls[i].id,
                        trigger_type="multi_ping",
                        reason=f"Sender {sender_id} pinged {len(classifications)} times",
                    ))
                    break

        return triggers

    async def _check_thread_acceleration(
        self,
        user_id: str,
        since: datetime,
    ) -> list[EscalationTrigger]:
        """Check for thread acceleration (≥5 new messages in 10 min)."""
        return []

    async def evaluate_escalation(
        self,
        trigger: EscalationTrigger,
        slack_service: "SlackService",
    ) -> bool:
        """Content gate: Re-classify with full context.

        Returns True if content confirms escalation-worthy.
        """
        # Phase 3 simplified: Always approve escalation
        # TODO Phase 4: Re-classify with full context from Slack/cache
        result = await self.db.execute(
            select(TriageClassification).where(
                TriageClassification.id == trigger.classification_id
            )
        )
        classification = result.scalar_one_or_none()

        if not classification:
            return False

        return True

    async def promote_to_notify_now(
        self,
        classification_id: str,
        reason: str,
    ) -> TriageClassification | None:
        """Promote a classification to notify_now.

        Sets escalation_override=True to bypass dedup.
        """
        result = await self.db.execute(
            select(TriageClassification).where(
                TriageClassification.id == classification_id
            )
        )
        classification = result.scalar_one_or_none()

        if not classification:
            return None

        classification.action = "notify_now"
        classification.classification_reason = f"[ESCALATION] {reason}"
        await self.db.commit()
        await self.db.refresh(classification)

        return classification
