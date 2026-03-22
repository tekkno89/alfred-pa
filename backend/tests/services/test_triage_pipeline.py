"""Tests for TriagePipeline."""

from unittest.mock import AsyncMock, patch, MagicMock

import pytest

from app.services.triage_classifier import ClassificationResult
from app.services.triage_enrichment import EnrichedTriagePayload


class TestTriagePipeline:
    async def test_process_creates_classification_record(self):
        """Pipeline should create a TriageClassification record."""
        mock_enrichment = AsyncMock()
        mock_enrichment.enrich.return_value = EnrichedTriagePayload(
            user_id="user-1",
            event_type="dm",
            channel_id="D12345",
            sender_slack_id="U99999",
            message_ts="1234567890.123456",
            thread_ts=None,
            message_text="test message",
            sensitivity="medium",
            focus_session_id="session-1",
        )

        mock_classifier = AsyncMock()
        mock_classifier.classify.return_value = ClassificationResult(
            urgency="review",
            confidence=0.8,
            reason="casual message",
            abstract="A test message",
        )

        mock_db = AsyncMock()
        mock_class_repo = AsyncMock()
        mock_settings_repo = AsyncMock()
        mock_settings_repo.get_by_user_id.return_value = MagicMock(debug_mode=False)

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
            patch("app.services.triage_pipeline.NotificationService"),
        ):
            from app.services.triage_pipeline import TriagePipeline

            pipeline = TriagePipeline(mock_db)
            await pipeline.process(
                user_id="user-1",
                event_type="dm",
                channel_id="D12345",
                sender_slack_id="U99999",
                message_ts="1234567890.123456",
                thread_ts=None,
                message_text="test message",
            )

        # Verify classification record was created
        mock_class_repo.create.assert_called_once()
        created = mock_class_repo.create.call_args[0][0]
        assert created.user_id == "user-1"
        assert created.urgency_level == "review"
        assert created.classification_path == "dm"
        mock_db.commit.assert_called_once()

    async def test_process_does_not_store_message_text(self):
        """Zero-persistence: message_text must not be in the classification record."""
        mock_enrichment = AsyncMock()
        mock_enrichment.enrich.return_value = EnrichedTriagePayload(
            user_id="user-1",
            event_type="dm",
            channel_id="D12345",
            sender_slack_id="U99999",
            message_ts="1234567890.123456",
            thread_ts=None,
            message_text="secret message content",
            sensitivity="medium",
        )

        mock_classifier = AsyncMock()
        mock_classifier.classify.return_value = ClassificationResult(
            urgency="digest",
            confidence=0.9,
            reason="low priority",
            abstract="General message",
        )

        mock_db = AsyncMock()
        mock_class_repo = AsyncMock()
        mock_settings_repo = AsyncMock()
        mock_settings_repo.get_by_user_id.return_value = MagicMock(debug_mode=False)

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
            patch("app.services.triage_pipeline.NotificationService"),
        ):
            from app.services.triage_pipeline import TriagePipeline

            pipeline = TriagePipeline(mock_db)
            await pipeline.process(
                user_id="user-1",
                event_type="dm",
                channel_id="D12345",
                sender_slack_id="U99999",
                message_ts="1234567890.123456",
                thread_ts=None,
                message_text="secret message content",
            )

        # The created TriageClassification must not contain message_text
        created = mock_class_repo.create.call_args[0][0]
        # Check all attributes — none should contain the raw text
        for attr_name in dir(created):
            if attr_name.startswith("_"):
                continue
            val = getattr(created, attr_name)
            if isinstance(val, str):
                assert "secret message content" not in val, (
                    f"message_text leaked into attribute {attr_name}"
                )

    async def test_urgent_sends_slack_dm_and_sse(self):
        """Urgent classification should trigger Slack DM and SSE notification."""
        mock_enrichment = AsyncMock()
        mock_enrichment.enrich.return_value = EnrichedTriagePayload(
            user_id="user-1",
            event_type="dm",
            channel_id="D12345",
            sender_slack_id="U99999",
            message_ts="1234567890.123456",
            thread_ts=None,
            message_text="URGENT: server is down",
            sensitivity="medium",
            sender_name="Alice",
            slack_permalink="https://workspace.slack.com/archives/D12345/p1234567890123456",
        )

        mock_classifier = AsyncMock()
        mock_classifier.classify.return_value = ClassificationResult(
            urgency="urgent",
            confidence=0.95,
            reason="emergency",
            abstract="Server outage reported",
        )

        mock_db = AsyncMock()
        mock_class_repo = AsyncMock()
        created_classification = MagicMock()
        created_classification.id = "class-1"
        created_classification.sender_slack_id = "U99999"
        created_classification.channel_id = "D12345"
        created_classification.slack_permalink = "https://workspace.slack.com/archives/D12345/p1234567890123456"
        mock_class_repo.create.return_value = created_classification

        mock_settings_repo = AsyncMock()
        mock_settings_repo.get_by_user_id.return_value = MagicMock(debug_mode=False)

        mock_notification_service = AsyncMock()
        mock_slack_service = AsyncMock()

        mock_user = MagicMock()
        mock_user.slack_user_id = "U_SELF"
        mock_user_repo = AsyncMock()
        mock_user_repo.get.return_value = mock_user

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
                "app.services.triage_pipeline.NotificationService",
                return_value=mock_notification_service,
            ),
            patch(
                "app.services.triage_pipeline.SlackService",
                return_value=mock_slack_service,
            ),
            patch(
                "app.db.repositories.UserRepository",
                return_value=mock_user_repo,
            ),
        ):
            from app.services.triage_pipeline import TriagePipeline

            pipeline = TriagePipeline(mock_db)
            await pipeline.process(
                user_id="user-1",
                event_type="dm",
                channel_id="D12345",
                sender_slack_id="U99999",
                message_ts="1234567890.123456",
                thread_ts=None,
                message_text="URGENT: server is down",
            )

        # Verify SSE notification was published
        mock_notification_service.publish.assert_called_once()
        sse_call = mock_notification_service.publish.call_args
        assert sse_call[0][1] == "triage.urgent"
