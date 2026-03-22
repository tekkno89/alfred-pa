"""Tests for TriageDeliveryService."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.triage_delivery import TriageDeliveryService


@pytest.fixture
def mock_db():
    return AsyncMock()


def _make_classification(**overrides):
    defaults = {
        "id": "class-1",
        "sender_slack_id": "U_SENDER",
        "channel_id": "C12345",
        "urgency_level": "review_at_break",
        "abstract": "Test message",
        "slack_permalink": "https://workspace.slack.com/archives/C12345/p123",
        "surfaced_at_break": False,
    }
    defaults.update(overrides)
    m = MagicMock(**defaults)
    return m


class TestDeliverBreakItems:
    async def test_delivers_items_via_slack_dm(self, mock_db):
        """Should send a Slack DM with unsurfaced break items."""
        items = [_make_classification(id=f"class-{i}") for i in range(3)]
        mock_user = MagicMock()
        mock_user.slack_user_id = "U_SELF"

        mock_slack = AsyncMock()

        with patch.object(TriageDeliveryService, "__init__", lambda self, db: None):
            service = TriageDeliveryService.__new__(TriageDeliveryService)
            service.db = mock_db
            service.class_repo = AsyncMock()
            service.class_repo.get_unsurfaced_break_items.return_value = items
            service.settings_repo = AsyncMock()
            service.user_repo = AsyncMock()
            service.user_repo.get.return_value = mock_user
            service.notification_service = AsyncMock()

            with patch(
                "app.services.triage_delivery.SlackService",
                return_value=mock_slack,
            ):
                count = await service.deliver_break_items("user-1", "session-1")

        assert count == 3
        service.class_repo.mark_surfaced_at_break.assert_called_once()
        mock_slack.send_message.assert_called_once()
        call_kwargs = mock_slack.send_message.call_args[1]
        assert call_kwargs["channel"] == "U_SELF"
        assert "3 message(s)" in call_kwargs["text"]

    async def test_returns_zero_when_no_items(self, mock_db):
        """Should return 0 when there are no unsurfaced items."""
        with patch.object(TriageDeliveryService, "__init__", lambda self, db: None):
            service = TriageDeliveryService.__new__(TriageDeliveryService)
            service.db = mock_db
            service.class_repo = AsyncMock()
            service.class_repo.get_unsurfaced_break_items.return_value = []
            service.settings_repo = AsyncMock()
            service.user_repo = AsyncMock()
            service.notification_service = AsyncMock()

            count = await service.deliver_break_items("user-1", "session-1")

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
            service.class_repo.get_unsurfaced_break_items.return_value = items
            service.settings_repo = AsyncMock()
            service.user_repo = AsyncMock()
            service.user_repo.get.return_value = mock_user
            service.notification_service = AsyncMock()

            with patch(
                "app.services.triage_delivery.SlackService",
                return_value=AsyncMock(),
            ):
                await service.deliver_break_items("user-1", "session-1")

        service.notification_service.publish.assert_called_once()
        sse_call = service.notification_service.publish.call_args
        assert sse_call[0][1] == "triage.break_check_slack"
        assert sse_call[0][2]["count"] == 1

    async def test_caps_slack_dm_at_ten_items(self, mock_db):
        """Should cap Slack DM lines at 10 items with overflow note."""
        items = [_make_classification(id=f"class-{i}") for i in range(15)]
        mock_user = MagicMock(slack_user_id="U_SELF")
        mock_slack = AsyncMock()

        with patch.object(TriageDeliveryService, "__init__", lambda self, db: None):
            service = TriageDeliveryService.__new__(TriageDeliveryService)
            service.db = mock_db
            service.class_repo = AsyncMock()
            service.class_repo.get_unsurfaced_break_items.return_value = items
            service.settings_repo = AsyncMock()
            service.user_repo = AsyncMock()
            service.user_repo.get.return_value = mock_user
            service.notification_service = AsyncMock()

            with patch(
                "app.services.triage_delivery.SlackService",
                return_value=mock_slack,
            ):
                count = await service.deliver_break_items("user-1", "session-1")

        assert count == 15
        text = mock_slack.send_message.call_args[1]["text"]
        assert "5 more" in text


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
        """Should send a Slack DM with digest grouped by urgency."""
        items = [
            _make_classification(urgency_level="urgent", abstract="Server down"),
            _make_classification(urgency_level="review_at_break", abstract="Meeting notes"),
            _make_classification(urgency_level="digest", abstract="Newsletter"),
        ]
        mock_user = MagicMock(slack_user_id="U_SELF")
        mock_slack = AsyncMock()

        with patch.object(TriageDeliveryService, "__init__", lambda self, db: None):
            service = TriageDeliveryService.__new__(TriageDeliveryService)
            service.db = mock_db
            service.class_repo = AsyncMock()
            service.class_repo.get_by_session.return_value = items
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
        assert "Urgent: 1" in text
        assert "Review: 1" in text
        assert "Low Priority: 1" in text

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
