"""Triage pipeline — processes messages through enrichment, classification, and delivery."""

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.triage import TriageClassification
from app.db.repositories.triage import (
    TriageClassificationRepository,
    TriageUserSettingsRepository,
)
from app.services.notifications import NotificationService
from app.services.slack import SlackService
from app.services.triage_classifier import TriageClassifier
from app.services.triage_enrichment import TriageEnrichmentService

logger = logging.getLogger(__name__)

PRIORITY_ORDER = {"p0": 0, "p1": 1, "p2": 2, "p3": 3}


class TriagePipeline:
    """Orchestrates the full triage flow: enrich -> classify -> store -> notify."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.enrichment = TriageEnrichmentService(db)
        self.class_repo = TriageClassificationRepository(db)
        self.settings_repo = TriageUserSettingsRepository(db)
        self.notification_service = NotificationService(db)

    async def process(
        self,
        user_id: str,
        event_type: str,
        channel_id: str,
        sender_slack_id: str,
        message_ts: str,
        thread_ts: str | None,
        message_text: str,
    ) -> None:
        """Process a single message through the triage pipeline.

        IMPORTANT: message_text is used in-memory for classification only.
        It is NEVER written to the database, Redis, or logs.
        """
        # 1. Enrich
        payload = await self.enrichment.enrich(
            user_id=user_id,
            event_type=event_type,
            channel_id=channel_id,
            sender_slack_id=sender_slack_id,
            message_ts=message_ts,
            thread_ts=thread_ts,
            message_text=message_text,
        )

        # Fetch settings once (used for filtering + debug mode)
        settings = await self.settings_repo.get_by_user_id(user_id)

        # 2. Classify
        classifier = TriageClassifier(
            sensitivity=payload.sensitivity,
            custom_classification_rules=payload.custom_classification_rules,
            p0_definition=payload.p0_definition,
            p1_definition=payload.p1_definition,
            p2_definition=payload.p2_definition,
            p3_definition=payload.p3_definition,
        )
        result = await classifier.classify(payload)

        # 2b. Always-on priority filter: drop items below threshold
        if payload.focus_session_id is None and result.priority != "review":
            min_priority = (
                settings.always_on_min_priority if settings else "p3"
            )
            result_order = PRIORITY_ORDER.get(result.priority)
            threshold_order = PRIORITY_ORDER.get(min_priority, 3)
            if result_order is not None and result_order > threshold_order:
                logger.debug(
                    f"[TRIAGE] Dropping {result.priority} (below threshold {min_priority}) "
                    f"for user={user_id}"
                )
                return

        # 3. Store classification (no message text)
        classification = TriageClassification(
            user_id=user_id,
            focus_session_id=payload.focus_session_id,
            focus_started_at=payload.focus_started_at,
            sender_slack_id=sender_slack_id,
            sender_name=payload.sender_name or None,
            channel_id=channel_id,
            channel_name=payload.channel_name or None,
            message_ts=message_ts,
            thread_ts=thread_ts,
            slack_permalink=payload.slack_permalink,
            priority_level=result.priority,
            confidence=result.confidence,
            classification_reason=result.reason,
            abstract=result.abstract,
            classification_path=event_type,
            keyword_matches=result.keyword_matches if result.keyword_matches else None,
        )
        classification = await self.class_repo.create(classification)
        await self.db.commit()

        # 4. Deliver P0 notifications
        if result.priority == "p0":
            await self._deliver_urgent(
                user_id=user_id,
                classification=classification,
                payload=payload,
                result=result,
            )

        # 5. Debug mode: enhanced logging and SSE payload (no raw text)
        if settings and settings.debug_mode:
            logger.debug(
                f"[TRIAGE DEBUG] user={user_id} "
                f"priority={result.priority} confidence={result.confidence:.2f} "
                f"reason={result.reason} path={event_type} "
                f"sender={sender_slack_id} channel={channel_id}"
            )
            try:
                await self.notification_service.publish(
                    user_id,
                    "triage.debug",
                    {
                        "classification_id": classification.id,
                        "priority": result.priority,
                        "confidence": result.confidence,
                        "reason": result.reason,
                        "path": event_type,
                    },
                )
            except Exception:
                logger.exception(f"Failed to publish debug SSE for user={user_id}")

        # message_text is now discarded (local variable goes out of scope)

    async def _deliver_urgent(
        self,
        user_id: str,
        classification: TriageClassification,
        payload,
        result,
    ) -> None:
        """Send P0 notification via Slack DM and SSE."""
        # Slack DM
        try:
            from app.db.repositories import UserRepository

            user_repo = UserRepository(self.db)
            user = await user_repo.get(user_id)
            if user and user.slack_user_id:
                slack_service = SlackService()
                sender_label = payload.sender_name or sender_slack_id_label(
                    classification.sender_slack_id
                )
                permalink_text = ""
                if classification.slack_permalink:
                    permalink_text = f"\n<{classification.slack_permalink}|View in Slack>"
                channel_info = ""
                if payload.event_type == "channel" and payload.channel_name:
                    channel_info = f" in #{payload.channel_name}"

                dm_text = (
                    f"*P0 — Urgent message from {sender_label}{channel_info}*\n"
                    f"{result.abstract}{permalink_text}"
                )
                await slack_service.send_message(
                    channel=user.slack_user_id,
                    text=dm_text,
                )
        except Exception:
            logger.exception(f"Failed to send urgent Slack DM for user={user_id}")

        # SSE notification
        try:
            await self.notification_service.publish(
                user_id,
                "triage.urgent",
                {
                    "classification_id": classification.id,
                    "sender_slack_id": classification.sender_slack_id,
                    "sender_name": payload.sender_name,
                    "channel_id": classification.channel_id,
                    "priority_level": "p0",
                    "abstract": result.abstract,
                    "slack_permalink": classification.slack_permalink,
                },
            )
        except Exception:
            logger.exception(f"Failed to publish SSE urgent event for user={user_id}")


def sender_slack_id_label(slack_id: str) -> str:
    """Format a Slack ID as a mention."""
    return f"<@{slack_id}>"
