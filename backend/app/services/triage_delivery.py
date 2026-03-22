"""Triage delivery — break notifications and post-focus digests."""

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.repositories import UserRepository
from app.db.repositories.triage import (
    TriageClassificationRepository,
    TriageUserSettingsRepository,
)
from app.services.notifications import NotificationService
from app.services.slack import SlackService

logger = logging.getLogger(__name__)


class TriageDeliveryService:
    """Delivers triage results at break time and focus-session end."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.class_repo = TriageClassificationRepository(db)
        self.settings_repo = TriageUserSettingsRepository(db)
        self.user_repo = UserRepository(db)
        self.notification_service = NotificationService(db)

    async def deliver_break_items(self, user_id: str, focus_session_id: str) -> int:
        """Deliver unsurfaced review_at_break items during a Pomodoro break.

        Returns the count of items delivered.
        """
        items = await self.class_repo.get_unsurfaced_break_items(
            user_id, focus_session_id
        )
        if not items:
            return 0

        # Mark as surfaced
        ids = [item.id for item in items]
        await self.class_repo.mark_surfaced_at_break(ids)
        await self.db.commit()

        # Send Slack DM with summary
        user = await self.user_repo.get(user_id)
        if user and user.slack_user_id:
            try:
                slack_service = SlackService()
                lines = [f"*You have {len(items)} message(s) to review:*\n"]
                for item in items[:10]:  # Cap at 10 in the DM
                    sender = item.sender_slack_id
                    link = f" <{item.slack_permalink}|View>" if item.slack_permalink else ""
                    abstract = item.abstract or "Message"
                    lines.append(f"- <@{sender}>: {abstract}{link}")
                if len(items) > 10:
                    lines.append(f"\n_...and {len(items) - 10} more_")

                await slack_service.send_message(
                    channel=user.slack_user_id,
                    text="\n".join(lines),
                )
            except Exception:
                logger.exception(f"Failed to send break items DM for user={user_id}")

        # SSE notification
        try:
            await self.notification_service.publish(
                user_id,
                "triage.break_check_slack",
                {"count": len(items)},
            )
        except Exception:
            logger.exception(f"Failed to publish break SSE for user={user_id}")

        return len(items)

    async def clear_break_notification(self, user_id: str) -> None:
        """Clear the break notification banner via SSE."""
        try:
            await self.notification_service.publish(
                user_id,
                "triage.break_notification_clear",
                {},
            )
        except Exception:
            logger.exception(f"Failed to clear break notification for user={user_id}")

    async def generate_and_send_digest(
        self, user_id: str, focus_session_id: str
    ) -> None:
        """Generate and send a post-focus digest for a session."""
        items = await self.class_repo.get_by_session(user_id, focus_session_id)
        if not items:
            return

        urgent_count = sum(1 for i in items if i.urgency_level == "urgent")
        review_count = sum(1 for i in items if i.urgency_level == "review_at_break")
        digest_count = sum(1 for i in items if i.urgency_level == "digest")

        # Send Slack DM digest
        user = await self.user_repo.get(user_id)
        if user and user.slack_user_id:
            try:
                slack_service = SlackService()

                header = "*Focus Session Triage Digest*\n"
                stats = (
                    f"Urgent: {urgent_count} | "
                    f"Review: {review_count} | "
                    f"Low Priority: {digest_count}\n"
                )

                lines = [header, stats]

                # Group by urgency
                for urgency_label, level in [
                    ("Urgent", "urgent"),
                    ("Review", "review_at_break"),
                ]:
                    level_items = [i for i in items if i.urgency_level == level]
                    if level_items:
                        lines.append(f"\n*{urgency_label}:*")
                        for item in level_items[:5]:
                            sender = item.sender_slack_id
                            link = (
                                f" <{item.slack_permalink}|View>"
                                if item.slack_permalink
                                else ""
                            )
                            abstract = item.abstract or "Message"
                            lines.append(f"- <@{sender}>: {abstract}{link}")
                        if len(level_items) > 5:
                            lines.append(f"  _...and {len(level_items) - 5} more_")

                await slack_service.send_message(
                    channel=user.slack_user_id,
                    text="\n".join(lines),
                )
            except Exception:
                logger.exception(f"Failed to send digest DM for user={user_id}")
