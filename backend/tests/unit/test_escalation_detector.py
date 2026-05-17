"""Unit tests for EscalationDetector service."""

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.escalation_detector import (
    EscalationDetector,
    EscalationTrigger,
    PING_WINDOW_MINUTES,
    THREAD_ACCELERATION_THRESHOLD,
    THREAD_ACCELERATION_WINDOW_MINUTES,
)


@pytest.fixture
def mock_db():
    return AsyncMock(spec=AsyncSession)


@pytest.fixture
def detector(mock_db):
    return EscalationDetector(mock_db)


class TestEscalationTriggerDataclass:
    def test_dataclass_fields(self):
        trigger = EscalationTrigger(
            classification_id="cls-123",
            trigger_type="multi_ping",
            reason="Sender U123 pinged 2 times",
        )
        assert trigger.classification_id == "cls-123"
        assert trigger.trigger_type == "multi_ping"
        assert trigger.reason == "Sender U123 pinged 2 times"

    def test_trigger_types(self):
        for trigger_type in ["multi_ping", "mention_added", "thread_acceleration"]:
            trigger = EscalationTrigger(
                classification_id="id",
                trigger_type=trigger_type,
                reason="test",
            )
            assert trigger.trigger_type == trigger_type


class TestConstants:
    def test_ping_window_minutes(self):
        assert PING_WINDOW_MINUTES == 5

    def test_thread_acceleration_threshold(self):
        assert THREAD_ACCELERATION_THRESHOLD == 5

    def test_thread_acceleration_window_minutes(self):
        assert THREAD_ACCELERATION_WINDOW_MINUTES == 10


class TestDetectEscalations:
    async def test_detect_escalations_returns_triggers(self, detector, mock_db):
        mock_cls1 = MagicMock()
        mock_cls1.id = "cls-1"
        mock_cls1.sender_slack_id = "U123"
        mock_cls1.created_at = datetime.utcnow() - timedelta(minutes=1)
        mock_cls1.action = "summarize_next"
        mock_cls1.reviewed_at = None

        mock_cls2 = MagicMock()
        mock_cls2.id = "cls-2"
        mock_cls2.sender_slack_id = "U123"
        mock_cls2.created_at = datetime.utcnow()
        mock_cls2.action = "summarize_next"
        mock_cls2.reviewed_at = None

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_cls1, mock_cls2]
        mock_db.execute.return_value = mock_result

        since = datetime.utcnow() - timedelta(hours=1)
        triggers = await detector.detect_escalations("user-1", since)

        assert len(triggers) == 1
        assert triggers[0].trigger_type == "multi_ping"
        assert "U123" in triggers[0].reason

    async def test_detect_escalations_no_pending(self, detector, mock_db):
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute.return_value = mock_result

        since = datetime.utcnow() - timedelta(hours=1)
        triggers = await detector.detect_escalations("user-1", since)

        assert triggers == []

    async def test_detect_escalations_filters_by_action(self, detector, mock_db):
        mock_cls = MagicMock()
        mock_cls.id = "cls-1"
        mock_cls.sender_slack_id = "U123"
        mock_cls.created_at = datetime.utcnow()
        mock_cls.action = "notify_now"
        mock_cls.reviewed_at = None

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute.return_value = mock_result

        since = datetime.utcnow() - timedelta(hours=1)
        triggers = await detector.detect_escalations("user-1", since)

        assert triggers == []


class TestCheckMultiPing:
    async def test_multi_ping_two_messages_within_window(self, detector):
        now = datetime.utcnow()
        cls1 = MagicMock()
        cls1.id = "cls-1"
        cls1.sender_slack_id = "U123"
        cls1.created_at = now - timedelta(minutes=2)

        cls2 = MagicMock()
        cls2.id = "cls-2"
        cls2.sender_slack_id = "U123"
        cls2.created_at = now

        triggers = await detector._check_multi_ping([cls1, cls2])

        assert len(triggers) == 1
        assert triggers[0].classification_id == "cls-2"
        assert triggers[0].trigger_type == "multi_ping"

    async def test_multi_ping_three_messages(self, detector):
        now = datetime.utcnow()
        cls1 = MagicMock()
        cls1.id = "cls-1"
        cls1.sender_slack_id = "U123"
        cls1.created_at = now - timedelta(minutes=4)

        cls2 = MagicMock()
        cls2.id = "cls-2"
        cls2.sender_slack_id = "U123"
        cls2.created_at = now - timedelta(minutes=2)

        cls3 = MagicMock()
        cls3.id = "cls-3"
        cls3.sender_slack_id = "U123"
        cls3.created_at = now

        triggers = await detector._check_multi_ping([cls1, cls2, cls3])

        assert len(triggers) == 1
        assert triggers[0].classification_id == "cls-2"

    async def test_multi_ping_messages_outside_window(self, detector):
        now = datetime.utcnow()
        cls1 = MagicMock()
        cls1.id = "cls-1"
        cls1.sender_slack_id = "U123"
        cls1.created_at = now - timedelta(minutes=10)

        cls2 = MagicMock()
        cls2.id = "cls-2"
        cls2.sender_slack_id = "U123"
        cls2.created_at = now

        triggers = await detector._check_multi_ping([cls1, cls2])

        assert len(triggers) == 0

    async def test_multi_ping_different_senders(self, detector):
        now = datetime.utcnow()
        cls1 = MagicMock()
        cls1.id = "cls-1"
        cls1.sender_slack_id = "U123"
        cls1.created_at = now - timedelta(minutes=1)

        cls2 = MagicMock()
        cls2.id = "cls-2"
        cls2.sender_slack_id = "U456"
        cls2.created_at = now

        triggers = await detector._check_multi_ping([cls1, cls2])

        assert len(triggers) == 0

    async def test_multi_ping_single_message(self, detector):
        cls1 = MagicMock()
        cls1.id = "cls-1"
        cls1.sender_slack_id = "U123"
        cls1.created_at = datetime.utcnow()

        triggers = await detector._check_multi_ping([cls1])

        assert len(triggers) == 0

    async def test_multi_ping_exactly_at_window_boundary(self, detector):
        now = datetime.utcnow()
        cls1 = MagicMock()
        cls1.id = "cls-1"
        cls1.sender_slack_id = "U123"
        cls1.created_at = now - timedelta(minutes=PING_WINDOW_MINUTES)

        cls2 = MagicMock()
        cls2.id = "cls-2"
        cls2.sender_slack_id = "U123"
        cls2.created_at = now

        triggers = await detector._check_multi_ping([cls1, cls2])

        assert len(triggers) == 1

    async def test_multi_ping_multiple_senders_trigger(self, detector):
        now = datetime.utcnow()
        cls1 = MagicMock()
        cls1.id = "cls-1"
        cls1.sender_slack_id = "U123"
        cls1.created_at = now - timedelta(minutes=1)

        cls2 = MagicMock()
        cls2.id = "cls-2"
        cls2.sender_slack_id = "U123"
        cls2.created_at = now

        cls3 = MagicMock()
        cls3.id = "cls-3"
        cls3.sender_slack_id = "U456"
        cls3.created_at = now - timedelta(minutes=1)

        cls4 = MagicMock()
        cls4.id = "cls-4"
        cls4.sender_slack_id = "U456"
        cls4.created_at = now

        triggers = await detector._check_multi_ping([cls1, cls2, cls3, cls4])

        assert len(triggers) == 2
        trigger_ids = {t.classification_id for t in triggers}
        assert "cls-2" in trigger_ids
        assert "cls-4" in trigger_ids


class TestCheckThreadAcceleration:
    async def test_thread_acceleration_returns_empty(self, detector, mock_db):
        since = datetime.utcnow() - timedelta(hours=1)
        triggers = await detector._check_thread_acceleration("user-1", since)

        assert triggers == []


class TestEvaluateEscalation:
    async def test_evaluate_escalation_classification_not_found(self, detector, mock_db):
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        trigger = EscalationTrigger(
            classification_id="missing-id",
            trigger_type="multi_ping",
            reason="test",
        )
        mock_slack = AsyncMock()

        result = await detector.evaluate_escalation(trigger, mock_slack)

        assert result is False

    async def test_evaluate_escalation_classification_found(self, detector, mock_db):
        mock_cls = MagicMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_cls
        mock_db.execute.return_value = mock_result

        trigger = EscalationTrigger(
            classification_id="cls-1",
            trigger_type="multi_ping",
            reason="test",
        )
        mock_slack = AsyncMock()

        result = await detector.evaluate_escalation(trigger, mock_slack)

        assert result is True


class TestPromoteToNotifyNow:
    async def test_promote_to_notify_now_success(self, detector, mock_db):
        mock_cls = MagicMock()
        mock_cls.id = "cls-1"
        mock_cls.action = "summarize_next"
        mock_cls.classification_reason = "original reason"

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_cls
        mock_db.execute.return_value = mock_result

        result = await detector.promote_to_notify_now("cls-1", "multi_ping detected")

        assert result is not None
        assert mock_cls.action == "notify_now"
        assert "[ESCALATION]" in mock_cls.classification_reason
        mock_db.commit.assert_called_once()
        mock_db.refresh.assert_called_once_with(mock_cls)

    async def test_promote_to_notify_now_not_found(self, detector, mock_db):
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        result = await detector.promote_to_notify_now("missing-id", "reason")

        assert result is None
        mock_db.commit.assert_not_called()

    async def test_promote_to_notify_now_appends_reason(self, detector, mock_db):
        mock_cls = MagicMock()
        mock_cls.id = "cls-1"
        mock_cls.action = "summarize_next"
        mock_cls.classification_reason = None

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_cls
        mock_db.execute.return_value = mock_result

        result = await detector.promote_to_notify_now("cls-1", "Sender U123 pinged 3 times")

        assert result is not None
        assert result.classification_reason == "[ESCALATION] Sender U123 pinged 3 times"
