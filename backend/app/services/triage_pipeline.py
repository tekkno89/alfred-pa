"""Triage pipeline — processes messages through enrichment, classification, and delivery.

ARCHITECTURE NOTE: Bot Message Filtering
========================================

Bot messages are short-circuited in TriagePipeline.process(), NOT in TriageEventRouter.

Why pipeline instead of router?
- The router's job is to determine WHO receives the message (which users are in focus mode
  or have is_always_on enabled). It enqueues ALL eligible messages.
- The pipeline's job is to determine WHAT action to take. It has access to classification
  logic and can short-circuit bot messages before expensive LLM calls.
- This separation keeps responsibilities clear: routing vs. classification.

Before this change:
- Bot messages were filtered in TriageEventRouter._should_triage() by checking
  event.get("bot_id") and returning False early.
- This caused issues with focus mode: if a user was in focus mode and a bot sent a message,
  the bot filter prevented the message from being enqueued at all, breaking focus mode
  behavior for legitimate human messages in the same channel.

After this change:
- Bot messages ARE enqueued by the router (same as human messages).
- The pipeline checks for bot_id and short-circuits to 'ignore' before LLM classification.
- Users can configure explicit bot rules (e.g., notify_now for PagerDuty) via
  ChannelSourceRule with entity_type='bot'.
- Focus mode continues to work correctly for all messages.

Expected behavior:
1. Bot message arrives -> router enqueues it -> pipeline sees bot_id -> checks for
   explicit rule -> if no rule, defaults to 'ignore' without LLM call.
2. Human message arrives -> router enqueues it -> pipeline processes normally -> LLM
   classification determines action.
"""

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.triage import TriageClassification
from app.db.repositories.triage import (
    ChannelSourceRuleRepository,
    TriageClassificationRepository,
    TriageUserSettingsRepository,
)
from app.services.active_hours_service import ActiveHoursService
from app.services.notifications import NotificationService
from app.services.slack import SlackService
from app.services.triage_classifier import ClassificationResult, TriageClassifier
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
        self.active_hours_service = ActiveHoursService(db)

    async def process(
        self,
        user_id: str,
        event_type: str,
        channel_id: str,
        sender_slack_id: str,
        message_ts: str,
        thread_ts: str | None,
        message_text: str,
        bot_id: str | None = None,
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
            bot_id=bot_id,
        )

        # Fetch settings once (used for filtering + debug mode)
        settings = await self.settings_repo.get_by_user_id(user_id)

        # Bot short-circuit: check for explicit bot rules before LLM classification
        if payload.is_bot and bot_id:
            bot_rule_repo = ChannelSourceRuleRepository(self.db)
            bot_rule = await bot_rule_repo.get_bot_rule(
                user_id=user_id, channel_id=channel_id, bot_id=bot_id
            )

            if bot_rule:
                action = bot_rule.action
                logger.info(
                    f"Bot rule short-circuit: bot={bot_id} action={action} "
                    f"user={user_id} channel={channel_id}"
                )
            else:
                action = "ignore"
                logger.info(
                    f"Bot message ignored (no rule): bot={bot_id} "
                    f"user={user_id} channel={channel_id}"
                )

            result = ClassificationResult(
                action=action,
                confidence=1.0,
                reason="Bot short-circuit",
                abstract="",
            )
        else:
            # 2. Classify via LLM
            classifier = TriageClassifier(
                sensitivity=payload.sensitivity,
                custom_classification_rules=payload.custom_classification_rules,
                p0_definition=payload.p0_definition,
                p1_definition=payload.p1_definition,
                p2_definition=payload.p2_definition,
                p3_definition=payload.p3_definition,
            )
            result = await classifier.classify(payload)

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
            action=result.action,
            review=result.review,
            confidence=result.confidence,
            classification_reason=result.reason,
            abstract=result.abstract,
            classification_path=event_type,
            keyword_matches=result.keyword_matches if result.keyword_matches else None,
        )

        action = result.action

        # Queue summarize_next and summarize_eod for digest
        if action in ("summarize_next", "summarize_eod"):
            classification.queued_for_digest = True
        else:
            classification.queued_for_digest = False

        classification = await self.class_repo.create(classification)
        await self.db.commit()

        if action == "notify_now":
            from app.services.alert_deduplication import AlertDeduplicationService

            dedup_service = AlertDeduplicationService(self.db)
            dedup_window = (
                settings.alert_dedup_window_minutes if settings else 30
            )

            should_alert = await dedup_service.should_alert(
                user_id=user_id,
                classification_id=classification.id,
                thread_ts=thread_ts,
                sender_slack_id=sender_slack_id,
                dedup_window_minutes=dedup_window,
            )

            if should_alert:
                from app.db.repositories import UserRepository
                from app.services.digest_response_checker import (
                    DigestResponseChecker,
                )

                user_repo = UserRepository(self.db)
                user = await user_repo.get(user_id)

                if user and user.slack_user_id:
                    checker = DigestResponseChecker(self.db)
                    user_responded = await checker._check_user_message_response(
                        user_id=user_id,
                        user_slack_id=user.slack_user_id,
                        conversation=None,
                        classification=classification,
                    )

                    if user_responded:
                        logger.info(
                            f"Skipping notify_now for classification {classification.id}: "
                            f"user already responded"
                        )
                        await self.db.commit()
                        return

                await self._deliver_urgent(
                    user_id=user_id,
                    classification=classification,
                    payload=payload,
                    result=result,
                )
                if not classification.queued_for_digest:
                    await dedup_service.mark_alerted(classification.id)
                await self.db.commit()
            else:
                logger.info(
                    f"notify_now alert deduplicated for classification {classification.id} "
                    f"(thread={thread_ts}, sender={sender_slack_id})"
                )

        if settings and settings.debug_mode:
            logger.debug(
                f"[TRIAGE DEBUG] user={user_id} "
                f"action={result.action} confidence={result.confidence:.2f} "
                f"reason={result.reason} path={event_type} "
                f"sender={sender_slack_id} channel={channel_id}"
            )
            try:
                await self.notification_service.publish(
                    user_id,
                    "triage.debug",
                    {
                        "classification_id": classification.id,
                        "action": result.action,
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
        # Check active hours
        should_deliver = await self.active_hours_service.should_deliver_now(
            user_id=user_id,
            action="notify_now",
        )

        if not should_deliver:
            logger.info(
                f"Outside active hours for user {user_id}, queuing notify_now message"
            )
            classification.queued_for_digest = True
            return

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
