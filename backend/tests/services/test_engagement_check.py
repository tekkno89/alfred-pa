"""Tests for engagement check in notify_now delivery."""

from unittest.mock import AsyncMock, patch, MagicMock
import pytest

from app.services.triage_classifier import ClassificationResult
from app.services.triage_enrichment import EnrichedTriagePayload
from app.db.models.triage import TriageClassification


class TestEngagementCheck:
    """Tests for the engagement check that gates notify_now delivery."""

    async def test_notify_now_skipped_if_user_responded(self):
        """notify_now should be skipped if user already responded to the message."""
        mock_enrichment = AsyncMock()
        mock_enrichment.enrich.return_value = EnrichedTriagePayload(
            user_id="user-1",
            event_type="dm",
            channel_id="D12345",
            sender_slack_id="U99999",
            message_ts="1234567890.123456",
            thread_ts=None,
            message_text="urgent question",
            sensitivity="medium",
            focus_session_id="session-1",
        )

        mock_classifier = AsyncMock()
        mock_classifier.classify.return_value = ClassificationResult(
            action="notify_now",
            confidence=0.9,
            reason="urgent",
            abstract="Urgent question",
        )

        mock_db = AsyncMock()
        mock_class_repo = AsyncMock()
        mock_class_repo.create.return_value = TriageClassification(
            id="class-1",
            user_id="user-1",
            channel_id="D12345",
            sender_slack_id="U99999",
            message_ts="1234567890.123456",
            action="notify_now",
            confidence=0.9,
        )
        mock_settings_repo = AsyncMock()
        mock_settings_repo.get_by_user_id.return_value = MagicMock(debug_mode=False)

        mock_user = MagicMock(id="user-1", slack_user_id="U12345")
        mock_checker = AsyncMock()
        mock_checker._check_user_message_response.return_value = True

        with (
            patch(
                "app.services.triage_pipeline.TriageEnrichmentService",
                return_value=mock_enrichment,
            ),
            patch(
                "app.services.triage_pipeline.TriageClassifier",
                return_value=mock_classifier,
            ),
            patch(
                "app.services.triage_pipeline.TriageClassificationRepository",
                return_value=mock_class_repo,
            ),
            patch(
                "app.services.triage_pipeline.TriageUserSettingsRepository",
                return_value=mock_settings_repo,
            ),
            patch(
                "app.services.triage_pipeline.NotificationService"
            ) as mock_notification_class,
            patch(
                "app.services.alert_deduplication.AlertDeduplicationService"
            ) as mock_dedup_class,
            patch("app.db.repositories.UserRepository") as mock_user_repo_class,
            patch(
                "app.services.digest_response_checker.DigestResponseChecker"
            ) as mock_checker_class,
        ):
            mock_dedup_class.return_value.should_alert = AsyncMock(return_value=True)
            mock_dedup_class.return_value.mark_alerted = AsyncMock()
            mock_user_repo_class.return_value.get = AsyncMock(return_value=mock_user)
            mock_checker_class.return_value = mock_checker
            mock_notification_class.return_value.publish = AsyncMock()

            from app.services.triage_pipeline import TriagePipeline

            pipeline = TriagePipeline(mock_db)
            await pipeline.process(
                user_id="user-1",
                event_type="dm",
                channel_id="D12345",
                sender_slack_id="U99999",
                message_ts="1234567890.123456",
                thread_ts=None,
                message_text="urgent question",
            )

        mock_checker._check_user_message_response.assert_called_once()
        mock_db.commit.assert_called()

    async def test_notify_now_delivered_if_user_not_responded(self):
        """notify_now should be delivered if user has not responded."""
        mock_enrichment = AsyncMock()
        mock_enrichment.enrich.return_value = EnrichedTriagePayload(
            user_id="user-1",
            event_type="dm",
            channel_id="D12345",
            sender_slack_id="U99999",
            message_ts="1234567890.123456",
            thread_ts=None,
            message_text="urgent question",
            sensitivity="medium",
            focus_session_id="session-1",
        )

        mock_classifier = AsyncMock()
        mock_classifier.classify.return_value = ClassificationResult(
            action="notify_now",
            confidence=0.9,
            reason="urgent",
            abstract="Urgent question",
        )

        mock_db = AsyncMock()
        mock_class_repo = AsyncMock()
        mock_class_repo.create.return_value = TriageClassification(
            id="class-1",
            user_id="user-1",
            channel_id="D12345",
            sender_slack_id="U99999",
            message_ts="1234567890.123456",
            action="notify_now",
            confidence=0.9,
        )
        mock_settings_repo = AsyncMock()
        mock_settings_repo.get_by_user_id.return_value = MagicMock(debug_mode=False)

        mock_user = MagicMock(id="user-1", slack_user_id="U12345")
        mock_checker = AsyncMock()
        mock_checker._check_user_message_response.return_value = False

        mock_slack = AsyncMock()

        with (
            patch(
                "app.services.triage_pipeline.TriageEnrichmentService",
                return_value=mock_enrichment,
            ),
            patch(
                "app.services.triage_pipeline.TriageClassifier",
                return_value=mock_classifier,
            ),
            patch(
                "app.services.triage_pipeline.TriageClassificationRepository",
                return_value=mock_class_repo,
            ),
            patch(
                "app.services.triage_pipeline.TriageUserSettingsRepository",
                return_value=mock_settings_repo,
            ),
            patch(
                "app.services.triage_pipeline.NotificationService"
            ) as mock_notification_class,
            patch(
                "app.services.alert_deduplication.AlertDeduplicationService"
            ) as mock_dedup_class,
            patch("app.db.repositories.UserRepository") as mock_user_repo_class,
            patch(
                "app.services.digest_response_checker.DigestResponseChecker"
            ) as mock_checker_class,
            patch("app.services.triage_pipeline.SlackService", return_value=mock_slack),
        ):
            mock_dedup_class.return_value.should_alert = AsyncMock(return_value=True)
            mock_dedup_class.return_value.mark_alerted = AsyncMock()
            mock_user_repo_class.return_value.get = AsyncMock(return_value=mock_user)
            mock_checker_class.return_value = mock_checker
            mock_notification_class.return_value.publish = AsyncMock()

            from app.services.triage_pipeline import TriagePipeline

            pipeline = TriagePipeline(mock_db)
            await pipeline.process(
                user_id="user-1",
                event_type="dm",
                channel_id="D12345",
                sender_slack_id="U99999",
                message_ts="1234567890.123456",
                thread_ts=None,
                message_text="urgent question",
            )

        mock_checker._check_user_message_response.assert_called_once()
        mock_slack.send_message.assert_called_once()

    async def test_notify_now_skipped_if_no_slack_user_id(self):
        """notify_now should be skipped if user has no Slack user ID (no DM to send to)."""
        mock_enrichment = AsyncMock()
        mock_enrichment.enrich.return_value = EnrichedTriagePayload(
            user_id="user-1",
            event_type="dm",
            channel_id="D12345",
            sender_slack_id="U99999",
            message_ts="1234567890.123456",
            thread_ts=None,
            message_text="urgent question",
            sensitivity="medium",
            focus_session_id="session-1",
        )

        mock_classifier = AsyncMock()
        mock_classifier.classify.return_value = ClassificationResult(
            action="notify_now",
            confidence=0.9,
            reason="urgent",
            abstract="Urgent question",
        )

        mock_db = AsyncMock()
        mock_class_repo = AsyncMock()
        mock_class_repo.create.return_value = TriageClassification(
            id="class-1",
            user_id="user-1",
            channel_id="D12345",
            sender_slack_id="U99999",
            message_ts="1234567890.123456",
            action="notify_now",
            confidence=0.9,
        )
        mock_settings_repo = AsyncMock()
        mock_settings_repo.get_by_user_id.return_value = MagicMock(debug_mode=False)

        mock_user = MagicMock(id="user-1", slack_user_id=None)
        mock_slack = AsyncMock()

        with (
            patch(
                "app.services.triage_pipeline.TriageEnrichmentService",
                return_value=mock_enrichment,
            ),
            patch(
                "app.services.triage_pipeline.TriageClassifier",
                return_value=mock_classifier,
            ),
            patch(
                "app.services.triage_pipeline.TriageClassificationRepository",
                return_value=mock_class_repo,
            ),
            patch(
                "app.services.triage_pipeline.TriageUserSettingsRepository",
                return_value=mock_settings_repo,
            ),
            patch(
                "app.services.triage_pipeline.NotificationService"
            ) as mock_notification_class,
            patch(
                "app.services.alert_deduplication.AlertDeduplicationService"
            ) as mock_dedup_class,
            patch("app.db.repositories.UserRepository") as mock_user_repo_class,
            patch("app.services.triage_pipeline.SlackService", return_value=mock_slack),
        ):
            mock_dedup_class.return_value.should_alert = AsyncMock(return_value=True)
            mock_dedup_class.return_value.mark_alerted = AsyncMock()
            mock_user_repo_class.return_value.get = AsyncMock(return_value=mock_user)
            mock_notification_class.return_value.publish = AsyncMock()

            from app.services.triage_pipeline import TriagePipeline

            pipeline = TriagePipeline(mock_db)
            await pipeline.process(
                user_id="user-1",
                event_type="dm",
                channel_id="D12345",
                sender_slack_id="U99999",
                message_ts="1234567890.123456",
                thread_ts=None,
                message_text="urgent question",
            )

        mock_slack.send_message.assert_not_called()
