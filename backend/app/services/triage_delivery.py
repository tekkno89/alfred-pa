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
        focus_mode: str | None = None,
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
            user_id, focus_session_id, focus_started_at, items,
            focus_mode=focus_mode,
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
        focus_mode: str | None = None,
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
                user_id, focus_session_id, focus_started_at, unconsolidated,
                focus_mode=focus_mode,
            )

        p0_count = sum(1 for i in all_items if i.priority_level == "p0")
        p1_count = sum(1 for i in all_items if i.priority_level == "p1")
        p2_count = sum(1 for i in all_items if i.priority_level == "p2")

        # Send Slack DM digest
        user = await self.user_repo.get(user_id)
        if user and user.slack_user_id:
            try:
                slack_service = SlackService()

                header = "*Focus Session Triage Digest*\n"
                stats = (
                    f"P0: {p0_count} | "
                    f"P1: {p1_count} | "
                    f"P2: {p2_count}\n"
                )

                lines = [header, stats]

                # Show P0 items
                p0_items = [i for i in all_items if i.priority_level == "p0"]
                if p0_items:
                    lines.append("\n*P0 (Urgent):*")
                    for item in p0_items[:5]:
                        sender = item.sender_slack_id
                        link = (
                            f" <{item.slack_permalink}|View>"
                            if item.slack_permalink
                            else ""
                        )
                        abstract = item.abstract or "Message"
                        lines.append(f"- <@{sender}>: {abstract}{link}")
                    if len(p0_items) > 5:
                        lines.append(f"  _...and {len(p0_items) - 5} more_")

                # Show P1 items
                p1_items = [i for i in all_items if i.priority_level == "p1"]
                if p1_items:
                    lines.append("\n*P1 (Important):*")
                    for item in p1_items[:10]:
                        sender = item.sender_slack_id
                        link = (
                            f" <{item.slack_permalink}|View>"
                            if item.slack_permalink
                            else ""
                        )
                        abstract = item.abstract or "Message"
                        lines.append(f"- <@{sender}>: {abstract}{link}")
                    if len(p1_items) > 10:
                        lines.append(f"  _...and {len(p1_items) - 10} more_")

                # Show P2 items
                p2_items = [i for i in all_items if i.priority_level == "p2"]
                if p2_items:
                    lines.append("\n*P2 (Notable):*")
                    for item in p2_items[:10]:
                        sender = item.sender_slack_id
                        link = (
                            f" <{item.slack_permalink}|View>"
                            if item.slack_permalink
                            else ""
                        )
                        abstract = item.abstract or "Message"
                        lines.append(f"- <@{sender}>: {abstract}{link}")
                    if len(p2_items) > 10:
                        lines.append(f"  _...and {len(p2_items) - 10} more_")

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
        focus_mode: str | None = None,
    ) -> TriageClassification:
        """Create a consolidated digest_summary row from individual digest items."""
        abstract = f"{len(items)} noteworthy messages"

        summary = TriageClassification(
            user_id=user_id,
            focus_session_id=focus_session_id,
            focus_started_at=focus_started_at,
            sender_slack_id="SYSTEM",
            sender_name=None,
            channel_id=items[0].channel_id,
            channel_name=None,
            message_ts=items[-1].message_ts,
            priority_level="digest_summary",
            confidence=1.0,
            classification_reason=f"Consolidated {len(items)} digest items",
            abstract=abstract,
            classification_path=focus_mode or "simple",
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

    # New methods for intelligent summary generation

    async def get_digest_items(
        self, user_id: str, priority: str
    ) -> list[TriageClassification]:
        """
        Get unalerted items for a priority digest.

        Args:
            user_id: User ID
            priority: Priority level (p1, p2, or p3)

        Returns:
            List of unalerted TriageClassification items
        """
        return await self.class_repo.get_unalerted_by_priority(user_id, priority)

    async def refetch_messages_for_digest(
        self, items: list[TriageClassification]
    ) -> list[dict]:
        """
        Re-fetch actual messages from Slack for digest summarization.

        Args:
            items: List of TriageClassification items

        Returns:
            List of message dicts with text, sender, channel, timestamp
        """
        slack_service = SlackService()
        messages = []

        for item in items[:20]:  # Cap at 20 messages to avoid rate limits
            try:
                # Fetch message from Slack using channel_id and message_ts
                if item.thread_ts:
                    # Fetch from thread
                    response = await slack_service.client.conversations_replies(
                        channel=item.channel_id,
                        ts=item.thread_ts,
                        latest=item.message_ts,
                        limit=1,
                        inclusive=True,
                    )
                else:
                    # Fetch standalone message
                    response = await slack_service.client.conversations_history(
                        channel=item.channel_id,
                        latest=item.message_ts,
                        limit=1,
                        inclusive=True,
                    )

                msg = response.get("messages", [{}])[0]
                text = msg.get("text", "")

                messages.append({
                    "text": text,
                    "sender_slack_id": item.sender_slack_id,
                    "sender_name": item.sender_name,
                    "channel_id": item.channel_id,
                    "channel_name": item.channel_name,
                    "message_ts": item.message_ts,
                    "thread_ts": item.thread_ts,
                    "permalink": item.slack_permalink,
                })
            except Exception as e:
                logger.warning(
                    f"Failed to fetch message {item.message_ts} in {item.channel_id}: {e}"
                )
                # Use stored abstract as fallback
                messages.append({
                    "text": item.abstract or "Message unavailable",
                    "sender_slack_id": item.sender_slack_id,
                    "sender_name": item.sender_name,
                    "channel_id": item.channel_id,
                    "channel_name": item.channel_name,
                    "message_ts": item.message_ts,
                    "thread_ts": item.thread_ts,
                    "permalink": item.slack_permalink,
                })

        return messages

    async def create_intelligent_summary(
        self, messages: list[dict], priority: str
    ) -> str:
        """
        Create an intelligent summary considering context across all messages.

        Args:
            messages: List of message dicts with text and metadata
            priority: Priority level (p1, p2, or p3)

        Returns:
            Intelligent summary string
        """
        if not messages:
            return "No messages to summarize"

        if len(messages) == 1:
            # Single message - use abstract directly
            return messages[0].get("text", "Message")

        # Multiple messages - use LLM to create contextual summary
        from app.core.llm import LLMMessage, get_llm_provider
        from app.core.config import get_settings

        settings = get_settings()
        location = settings.triage_vertex_location or None
        provider = get_llm_provider(settings.triage_synthesis_model or "gemini-2.5-flash", location=location)

        # Build message list for LLM
        message_list = []
        for i, msg in enumerate(messages[:20], 1):
            sender = msg.get("sender_name") or f"<@{msg.get('sender_slack_id')}>"
            channel = msg.get("channel_name") or msg.get("channel_id")
            text = msg.get("text", "")[:200]  # Truncate long messages
            message_list.append(f"{i}. {sender} in #{channel}: {text}")

        system_prompt = f"""You are creating a concise summary of {len(messages)} Slack messages for a user digest.

Priority level: {priority.upper()}

Messages:
{chr(10).join(message_list)}

Create a brief 2-3 sentence summary that:
1. Identifies common themes or threads across messages
2. Highlights any urgent or time-sensitive items
3. Mentions key senders or channels involved

Do NOT quote messages directly. Focus on the overall picture.
Format: "Overall summary of key topics and any urgent items."

If there are no common themes, just summarize: "You have {len(messages)} messages from [senders] in [channels]." """

        try:
            response = await provider.generate(
                messages=[
                    LLMMessage(role="user", content=system_prompt),
                ],
                temperature=0.3,
                max_tokens=200,
            )
            return response.strip()
        except Exception as e:
            logger.exception(f"Failed to create intelligent summary: {e}")
            # Fallback: simple summary
            senders = set(msg.get("sender_name") or msg.get("sender_slack_id") for msg in messages)
            channels = set(msg.get("channel_name") or msg.get("channel_id") for msg in messages)
            return f"You have {len(messages)} messages from {len(senders)} senders in {len(channels)} channels."

    async def send_priority_digest_dm(
        self,
        user_id: str,
        summary: str,
        items: list[TriageClassification],
        priority: str,
        digest_type: str,
    ) -> None:
        """
        Send a digest DM for a specific priority level.

        Args:
            user_id: User ID
            summary: Intelligent summary of messages
            items: List of TriageClassification items
            priority: Priority level (p1, p2, or p3)
            digest_type: Type of digest (scheduled, interval, daily)
        """
        user = await self.user_repo.get(user_id)
        if not user or not user.slack_user_id:
            return

        try:
            slack_service = SlackService()

            priority_labels = {
                "p1": "P1 — Important",
                "p2": "P2 — Notable",
                "p3": "P3 — Daily Digest",
            }

            digest_type_labels = {
                "scheduled": "Scheduled",
                "interval": "Interval",
                "daily": "Daily",
            }

            header = f"*{priority_labels.get(priority, priority)} {digest_type_labels.get(digest_type, digest_type)} Digest*\n"
            summary_line = f"{summary}\n"
            lines = [header, summary_line]

            # List individual items
            lines.append(f"You have {len(items)} message(s):\n")
            for item in items[:20]:
                sender = item.sender_slack_id
                link = f" <{item.slack_permalink}|View>" if item.slack_permalink else ""
                abstract = item.abstract or "Message"
                lines.append(f"- <@{sender}>: {abstract}{link}")

            if len(items) > 20:
                lines.append(f"\n_...and {len(items) - 20} more_")

            await slack_service.send_message(
                channel=user.slack_user_id,
                text="\n".join(lines),
            )
        except Exception:
            logger.exception(f"Failed to send {priority} digest DM for user={user_id}")
