"""Tests for TriageDeliveryService."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.triage_delivery import TriageDeliveryService


@pytest.fixture
def mock_db():
    return AsyncMock()


def _make_classification(**overrides):
    from datetime import datetime

    defaults = {
        "id": "class-1",
        "sender_slack_id": "U_SENDER",
        "sender_name": "Sender",
        "channel_id": "C12345",
        "channel_name": "general",
        "priority_level": "p2",
        "abstract": "Test message",
        "slack_permalink": "https://workspace.slack.com/archives/C12345/p123",
        "surfaced_at_break": False,
        "classification_path": "channel",
        "message_ts": "1234567890.123456",
        "confidence": 0.8,
        "created_at": datetime.utcnow(),
    }
    defaults.update(overrides)
    m = MagicMock(**defaults)
    # Make confidence and created_at comparable
    m.confidence = defaults["confidence"]
    m.created_at = defaults["created_at"]
    return m


class TestDeliverSessionDigest:
    async def test_delivers_items_and_creates_summary(self, mock_db):
        """Should create a digest summary and send Slack DM."""
        items = [_make_classification(id=f"class-{i}") for i in range(3)]
        mock_user = MagicMock()
        mock_user.slack_user_id = "U_SELF"

        mock_slack = AsyncMock()

        with patch.object(TriageDeliveryService, "__init__", lambda self, db: None):
            service = TriageDeliveryService.__new__(TriageDeliveryService)
            service.db = mock_db
            service.class_repo = AsyncMock()
            service.class_repo.get_unsurfaced_digest_items.return_value = items
            # _create_digest_summary needs to work — mock the create and link
            mock_summary = MagicMock(id="summary-1")
            service.class_repo.create.return_value = mock_summary
            service.class_repo.link_to_summary = AsyncMock()
            service.settings_repo = AsyncMock()
            service.user_repo = AsyncMock()
            service.user_repo.get.return_value = mock_user
            service.notification_service = AsyncMock()

            with patch(
                "app.services.triage_delivery.SlackService",
                return_value=mock_slack,
            ):
                count = await service.deliver_session_digest("user-1", "session-1")

        assert count == 3
        service.class_repo.mark_surfaced_at_break.assert_called_once()
        mock_slack.send_message.assert_called_once()

    async def test_returns_zero_when_no_items(self, mock_db):
        """Should return 0 when there are no unsurfaced items."""
        with patch.object(TriageDeliveryService, "__init__", lambda self, db: None):
            service = TriageDeliveryService.__new__(TriageDeliveryService)
            service.db = mock_db
            service.class_repo = AsyncMock()
            service.class_repo.get_unsurfaced_digest_items.return_value = []
            service.settings_repo = AsyncMock()
            service.user_repo = AsyncMock()
            service.notification_service = AsyncMock()

            count = await service.deliver_session_digest("user-1", "session-1")

        assert count == 0
        service.class_repo.mark_surfaced_at_break.assert_not_called()

    async def test_publishes_sse_event(self, mock_db):
        """Should publish triage.break_check_slack SSE event."""
        items = [_make_classification()]
        mock_user = MagicMock(slack_user_id="U_SELF")

        with patch.object(TriageDeliveryService, "__init__", lambda self, db: None):
            service = TriageDeliveryService.__new__(TriageDeliveryService)
            service.db = mock_db
            service.class_repo = AsyncMock()
            service.class_repo.get_unsurfaced_digest_items.return_value = items
            mock_summary = MagicMock(id="summary-1")
            service.class_repo.create.return_value = mock_summary
            service.class_repo.link_to_summary = AsyncMock()
            service.settings_repo = AsyncMock()
            service.user_repo = AsyncMock()
            service.user_repo.get.return_value = mock_user
            service.notification_service = AsyncMock()

            with patch(
                "app.services.triage_delivery.SlackService",
                return_value=AsyncMock(),
            ):
                await service.deliver_session_digest("user-1", "session-1")

        service.notification_service.publish.assert_called_once()
        sse_call = service.notification_service.publish.call_args
        assert sse_call[0][1] == "triage.break_check_slack"
        assert sse_call[0][2]["count"] == 1


class TestClearBreakNotification:
    async def test_publishes_clear_event(self, mock_db):
        """Should publish triage.break_notification_clear SSE event."""
        with patch.object(TriageDeliveryService, "__init__", lambda self, db: None):
            service = TriageDeliveryService.__new__(TriageDeliveryService)
            service.db = mock_db
            service.notification_service = AsyncMock()

            await service.clear_break_notification("user-1")

        service.notification_service.publish.assert_called_once_with(
            "user-1", "triage.break_notification_clear", {}
        )


class TestGenerateAndSendDigest:
    async def test_sends_digest_dm(self, mock_db):
        """Should send a Slack DM with digest grouped by priority."""
        from datetime import datetime

        items = [
            _make_classification(
                priority_level="p0", abstract="Server down", confidence=0.9
            ),
            _make_classification(
                priority_level="p1", abstract="Meeting notes", confidence=0.8
            ),
            _make_classification(
                priority_level="p3", abstract="Newsletter", confidence=0.6
            ),
        ]
        mock_user = MagicMock(slack_user_id="U_SELF")
        mock_slack = AsyncMock()

        with patch.object(TriageDeliveryService, "__init__", lambda self, db: None):
            service = TriageDeliveryService.__new__(TriageDeliveryService)
            service.db = mock_db
            service.class_repo = AsyncMock()
            service.class_repo.get_by_session.return_value = items
            service.class_repo.get_unsurfaced_digest_items.return_value = []
            service.settings_repo = AsyncMock()
            service.user_repo = AsyncMock()
            service.user_repo.get.return_value = mock_user
            service.notification_service = AsyncMock()

            with patch(
                "app.services.triage_delivery.SlackService",
                return_value=mock_slack,
            ):
                await service.generate_and_send_digest("user-1", "session-1")

        mock_slack.send_message.assert_called_once()
        text = mock_slack.send_message.call_args[1]["text"]
        assert "Focus Session Triage Digest" in text
        # P0 should not appear in digest (instantly notified during focus)
        assert "P0: 1" not in text
        assert "P1: 1" in text
        assert "P2: 0" in text

    async def test_shows_top_3_by_confidence(self, mock_db):
        """Should show top 3 items sorted by confidence score."""
        from datetime import datetime

        items = [
            _make_classification(
                id="p1-low",
                priority_level="p1",
                abstract="Low priority",
                confidence=0.5,
            ),
            _make_classification(
                id="p1-high",
                priority_level="p1",
                abstract="High priority",
                confidence=0.95,
            ),
            _make_classification(
                id="p1-mid",
                priority_level="p1",
                abstract="Mid priority",
                confidence=0.75,
            ),
            _make_classification(
                id="p1-vlow", priority_level="p1", abstract="Very low", confidence=0.3
            ),
            _make_classification(
                id="p1-vhigh",
                priority_level="p1",
                abstract="Very high",
                confidence=0.85,
            ),
        ]
        mock_user = MagicMock(slack_user_id="U_SELF")
        mock_slack = AsyncMock()

        with patch.object(TriageDeliveryService, "__init__", lambda self, db: None):
            service = TriageDeliveryService.__new__(TriageDeliveryService)
            service.db = mock_db
            service.class_repo = AsyncMock()
            service.class_repo.get_by_session.return_value = items
            service.class_repo.get_unsurfaced_digest_items.return_value = []
            service.settings_repo = AsyncMock()
            service.user_repo = AsyncMock()
            service.user_repo.get.return_value = mock_user
            service.notification_service = AsyncMock()

            with patch(
                "app.services.triage_delivery.SlackService",
                return_value=mock_slack,
            ):
                await service.generate_and_send_digest("user-1", "session-1")

        text = mock_slack.send_message.call_args[1]["text"]
        # Should show top 3 (high 0.95, vhigh 0.85, mid 0.75)
        assert "High priority" in text
        assert "Very high" in text
        assert "Mid priority" in text
        # Should not show lower confidence items
        assert "Low priority" not in text
        assert "Very low" not in text
        # Should show remaining count
        assert "2 more P1 messages" in text
        assert "Check Alfred Triage" in text

    async def test_no_digest_when_no_items(self, mock_db):
        """Should not send anything when there are no classifications."""
        with patch.object(TriageDeliveryService, "__init__", lambda self, db: None):
            service = TriageDeliveryService.__new__(TriageDeliveryService)
            service.db = mock_db
            service.class_repo = AsyncMock()
            service.class_repo.get_by_session.return_value = []
            service.settings_repo = AsyncMock()
            service.user_repo = AsyncMock()
            service.notification_service = AsyncMock()

            await service.generate_and_send_digest("user-1", "session-1")

        service.user_repo.get.assert_not_called()
