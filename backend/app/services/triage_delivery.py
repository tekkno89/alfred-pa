"""Triage delivery — break notifications and post-focus digests."""

import logging
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.triage import TriageClassification
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

    async def deliver_session_digest(
        self,
        user_id: str,
        focus_session_id: str,
        focus_started_at: datetime | None = None,
    ) -> int:
        """Consolidate and deliver digest items for a focus/pomodoro session.

        Called at pomodoro work→break transitions and simple focus end.
        Returns the count of items consolidated.
        """
        items = await self.class_repo.get_unsurfaced_digest_items(
            user_id, focus_session_id, focus_started_at
        )
        if not items:
            return 0

        # Mark as surfaced
        ids = [item.id for item in items]
        await self.class_repo.mark_surfaced_at_break(ids)

        # Create consolidated digest summary
        summary = await self._create_digest_summary(
            user_id, focus_session_id, focus_started_at, items
        )

        await self.db.commit()

        # Send Slack DM with digest
        await self._send_digest_dm(user_id, items, "Pomodoro Session Digest")

        # SSE notification
        try:
            await self.notification_service.publish(
                user_id,
                "triage.break_check_slack",
                {"count": len(items), "summary_id": summary.id if summary else None},
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
        self,
        user_id: str,
        focus_session_id: str,
        focus_started_at: datetime | None = None,
    ) -> None:
        """Generate and send a post-focus digest for a session."""
        # Get all items for the session (for stats in the DM)
        all_items = await self.class_repo.get_by_session(
            user_id, focus_session_id, focus_started_at
        )
        if not all_items:
            return

        # Consolidate any remaining unconsolidated digest items
        unconsolidated = await self.class_repo.get_unsurfaced_digest_items(
            user_id, focus_session_id, focus_started_at
        )
        if unconsolidated:
            ids = [item.id for item in unconsolidated]
            await self.class_repo.mark_surfaced_at_break(ids)
            await self._create_digest_summary(
                user_id, focus_session_id, focus_started_at, unconsolidated
            )

        urgent_count = sum(1 for i in all_items if i.urgency_level == "urgent")
        digest_count = sum(
            1 for i in all_items if i.urgency_level in ("digest", "digest_summary")
        )

        # Send Slack DM digest
        user = await self.user_repo.get(user_id)
        if user and user.slack_user_id:
            try:
                slack_service = SlackService()

                header = "*Focus Session Triage Digest*\n"
                stats = (
                    f"Urgent: {urgent_count} | "
                    f"Digest: {digest_count}\n"
                )

                lines = [header, stats]

                # Show urgent items
                urgent_items = [i for i in all_items if i.urgency_level == "urgent"]
                if urgent_items:
                    lines.append("\n*Urgent:*")
                    for item in urgent_items[:5]:
                        sender = item.sender_slack_id
                        link = (
                            f" <{item.slack_permalink}|View>"
                            if item.slack_permalink
                            else ""
                        )
                        abstract = item.abstract or "Message"
                        lines.append(f"- <@{sender}>: {abstract}{link}")
                    if len(urgent_items) > 5:
                        lines.append(f"  _...and {len(urgent_items) - 5} more_")

                # Show digest items
                digest_items = [i for i in all_items if i.urgency_level == "digest"]
                if digest_items:
                    lines.append("\n*Digest:*")
                    for item in digest_items[:10]:
                        sender = item.sender_slack_id
                        link = (
                            f" <{item.slack_permalink}|View>"
                            if item.slack_permalink
                            else ""
                        )
                        abstract = item.abstract or "Message"
                        lines.append(f"- <@{sender}>: {abstract}{link}")
                    if len(digest_items) > 10:
                        lines.append(f"  _...and {len(digest_items) - 10} more_")

                await slack_service.send_message(
                    channel=user.slack_user_id,
                    text="\n".join(lines),
                )
            except Exception:
                logger.exception(f"Failed to send digest DM for user={user_id}")

    async def _create_digest_summary(
        self,
        user_id: str,
        focus_session_id: str,
        focus_started_at: datetime | None,
        items: list[TriageClassification],
    ) -> TriageClassification:
        """Create a consolidated digest_summary row from individual digest items."""
        senders: set[str] = set()
        channels: set[str] = set()
        summary_lines: list[str] = []

        for item in items:
            senders.add(item.sender_name or item.sender_slack_id)
            if item.channel_name:
                channels.add(item.channel_name)
            if item.abstract:
                sender_label = item.sender_name or item.sender_slack_id
                summary_lines.append(f"- {sender_label}: {item.abstract}")

        channel_list = (
            ", ".join(f"#{c}" for c in sorted(channels)) if channels else "DMs"
        )
        abstract = (
            f"{len(items)} noteworthy message(s) from "
            f"{len(senders)} sender(s) in {channel_list}."
        )
        if summary_lines:
            abstract += "\n" + "\n".join(summary_lines[:10])
            if len(summary_lines) > 10:
                abstract += f"\n...and {len(summary_lines) - 10} more"

        summary = TriageClassification(
            user_id=user_id,
            focus_session_id=focus_session_id,
            focus_started_at=focus_started_at,
            sender_slack_id="SYSTEM",
            sender_name="Digest Summary",
            channel_id=items[0].channel_id,
            channel_name=None,
            message_ts=items[-1].message_ts,
            urgency_level="digest_summary",
            confidence=1.0,
            classification_reason=f"Consolidated {len(items)} digest items",
            abstract=abstract,
            classification_path=items[0].classification_path,
            child_count=len(items),
        )
        summary = await self.class_repo.create(summary)

        # Link children to summary
        child_ids = [item.id for item in items]
        await self.class_repo.link_to_summary(child_ids, summary.id)

        return summary

    async def _send_digest_dm(
        self,
        user_id: str,
        items: list[TriageClassification],
        header_text: str,
    ) -> None:
        """Send a Slack DM listing digest items with summaries and links."""
        user = await self.user_repo.get(user_id)
        if not user or not user.slack_user_id:
            return

        try:
            slack_service = SlackService()
            lines = [f"*{header_text}*\n"]
            lines.append(f"You have {len(items)} message(s) to review:\n")
            for item in items[:10]:
                sender = item.sender_slack_id
                link = (
                    f" <{item.slack_permalink}|View>" if item.slack_permalink else ""
                )
                abstract = item.abstract or "Message"
                lines.append(f"- <@{sender}>: {abstract}{link}")
            if len(items) > 10:
                lines.append(f"\n_...and {len(items) - 10} more_")

            await slack_service.send_message(
                channel=user.slack_user_id,
                text="\n".join(lines),
            )
        except Exception:
            logger.exception(f"Failed to send digest DM for user={user_id}")
