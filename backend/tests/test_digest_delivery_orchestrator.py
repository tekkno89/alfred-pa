"""Tests for digest delivery orchestrator."""

import pytest
from datetime import datetime, timedelta, UTC
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.digest_delivery_orchestrator import (
    DeliveryTrigger,
    DeliveryTriggerPlugin,
    CalendarEndTrigger,
    IdleTrigger,
    StaleQueueTrigger,
    DigestDeliveryOrchestrator,
    STALE_QUEUE_THRESHOLD_MINUTES,
)


class TestDeliveryTrigger:
    """Tests for DeliveryTrigger dataclass."""

    def test_create_trigger(self):
        """Test creating a delivery trigger."""
        now = datetime.utcnow()
        trigger = DeliveryTrigger(
            trigger_type="test",
            user_id="user-123",
            triggered_at=now,
            metadata={"key": "value"},
        )

        assert trigger.trigger_type == "test"
        assert trigger.user_id == "user-123"
        assert trigger.triggered_at == now
        assert trigger.metadata == {"key": "value"}

    def test_create_trigger_default_metadata(self):
        """Test creating a trigger with default empty metadata."""
        trigger = DeliveryTrigger(
            trigger_type="test",
            user_id="user-123",
            triggered_at=datetime.utcnow(),
        )

        assert trigger.metadata == {}


class TestStaleQueueTrigger:
    """Tests for StaleQueueTrigger."""

    @pytest.mark.asyncio
    async def test_no_stale_items(self, db_session):
        """Test returns None when no stale items exist."""
        trigger = StaleQueueTrigger(stale_threshold_minutes=30)

        result = await trigger.check("user-123", db_session)

        assert result is None

    @pytest.mark.asyncio
    async def test_has_stale_items(self, db_session, test_user):
        """Test returns trigger when stale items exist."""
        from app.db.models.triage import TriageClassification

        old_time = datetime.utcnow() - timedelta(minutes=45)
        classification = TriageClassification(
            user_id=test_user.id,
            sender_slack_id="U123",
            channel_id="C123",
            channel_name="test",
            message_ts="1234567890.123",
            action="summarize_next",
            classification_path="dm",
            queued_for_digest=True,
            created_at=old_time,
        )
        db_session.add(classification)
        await db_session.commit()

        trigger = StaleQueueTrigger(stale_threshold_minutes=30)
        result = await trigger.check(test_user.id, db_session)

        assert result is not None
        assert result.trigger_type == "stale_queue"
        assert result.user_id == test_user.id
        assert "oldest_item_age_minutes" in result.metadata

    @pytest.mark.asyncio
    async def test_recent_items_not_stale(self, db_session, test_user):
        """Test returns None for recent items."""
        from app.db.models.triage import TriageClassification

        recent_time = datetime.utcnow() - timedelta(minutes=10)
        classification = TriageClassification(
            user_id=test_user.id,
            sender_slack_id="U123",
            channel_id="C123",
            channel_name="test",
            message_ts="1234567890.123",
            action="summarize_next",
            classification_path="dm",
            queued_for_digest=True,
            created_at=recent_time,
        )
        db_session.add(classification)
        await db_session.commit()

        trigger = StaleQueueTrigger(stale_threshold_minutes=30)
        result = await trigger.check(test_user.id, db_session)

        assert result is None

    @pytest.mark.asyncio
    async def test_ignores_non_summarize_next(self, db_session, test_user):
        """Test ignores items with other actions."""
        from app.db.models.triage import TriageClassification

        old_time = datetime.utcnow() - timedelta(minutes=45)
        classification = TriageClassification(
            user_id=test_user.id,
            sender_slack_id="U123",
            channel_id="C123",
            channel_name="test",
            message_ts="1234567890.123",
            action="notify_now",
            classification_path="dm",
            queued_for_digest=True,
            created_at=old_time,
        )
        db_session.add(classification)
        await db_session.commit()

        trigger = StaleQueueTrigger(stale_threshold_minutes=30)
        result = await trigger.check(test_user.id, db_session)

        assert result is None


class TestIdleTrigger:
    """Tests for IdleTrigger (placeholder)."""

    @pytest.mark.asyncio
    async def test_always_returns_none(self, db_session):
        """Test placeholder always returns None."""
        trigger = IdleTrigger()

        result = await trigger.check("user-123", db_session)

        assert result is None

    def test_name_property(self):
        """Test name property."""
        trigger = IdleTrigger()
        assert trigger.name == "idle_detection"


class TestCalendarEndTrigger:
    """Tests for CalendarEndTrigger."""

    @pytest.mark.asyncio
    async def test_no_google_calendar_token(self, db_session):
        """Test returns None when user has no Google Calendar token."""
        trigger = CalendarEndTrigger()

        with patch(
            "app.services.digest_delivery_orchestrator.GoogleCalendarService"
        ) as MockService:
            mock_instance = MockService.return_value
            mock_instance.get_valid_token = AsyncMock(return_value=None)

            result = await trigger.check("user-123", db_session)

            assert result is None

    def test_name_property(self):
        """Test name property."""
        trigger = CalendarEndTrigger()
        assert trigger.name == "calendar_end"

    def test_find_next_event_returns_none_for_empty_list(self):
        """Test _find_next_event returns None when no events."""
        trigger = CalendarEndTrigger()
        result = trigger._find_next_event([], datetime.now(UTC))
        assert result is None


class TestDigestDeliveryOrchestrator:
    """Tests for DigestDeliveryOrchestrator."""

    @pytest.mark.asyncio
    async def test_check_triggers_no_pending(self, db_session):
        """Test check_triggers returns None when no triggers fire."""
        orchestrator = DigestDeliveryOrchestrator(db_session)

        result = await orchestrator.check_triggers("user-123")

        assert result is None

    @pytest.mark.asyncio
    async def test_get_users_with_pending_items_empty(self, db_session):
        """Test returns empty list when no pending items."""
        orchestrator = DigestDeliveryOrchestrator(db_session)

        result = await orchestrator.get_users_with_pending_items()

        assert result == []

    @pytest.mark.asyncio
    async def test_get_users_with_pending_items(self, db_session, test_user):
        """Test returns users with pending summarize_next items."""
        from app.db.models.triage import TriageClassification

        classification = TriageClassification(
            user_id=test_user.id,
            sender_slack_id="U123",
            channel_id="C123",
            channel_name="test",
            message_ts="1234567890.123",
            action="summarize_next",
            classification_path="dm",
            queued_for_digest=True,
        )
        db_session.add(classification)
        await db_session.commit()

        orchestrator = DigestDeliveryOrchestrator(db_session)
        result = await orchestrator.get_users_with_pending_items()

        assert test_user.id in result

    @pytest.mark.asyncio
    async def test_deliver_summarize_next_focus_mode(self, db_session, test_user):
        """Test skips delivery when user is in focus mode."""
        from app.db.models.focus import FocusModeState

        state = FocusModeState(
            user_id=test_user.id,
            is_active=True,
            mode="simple",
            started_at=datetime.utcnow(),
        )
        db_session.add(state)
        await db_session.commit()

        orchestrator = DigestDeliveryOrchestrator(db_session)
        trigger = DeliveryTrigger(
            trigger_type="stale_queue",
            user_id=test_user.id,
            triggered_at=datetime.utcnow(),
        )

        result = await orchestrator.deliver_summarize_next(test_user.id, trigger)

        assert result["status"] == "skipped_focus_mode"

    @pytest.mark.asyncio
    async def test_deliver_summarize_next_no_items(self, db_session, test_user):
        """Test returns no_items when nothing to deliver."""
        orchestrator = DigestDeliveryOrchestrator(db_session)
        trigger = DeliveryTrigger(
            trigger_type="stale_queue",
            user_id=test_user.id,
            triggered_at=datetime.utcnow(),
        )

        result = await orchestrator.deliver_summarize_next(test_user.id, trigger)

        assert result["status"] == "no_items"

    @pytest.mark.asyncio
    async def test_deliver_eod_digest_not_enabled(self, db_session, test_user):
        """Test skips EOD when triage not enabled."""
        orchestrator = DigestDeliveryOrchestrator(db_session)

        result = await orchestrator.deliver_eod_digest(test_user.id)

        assert result["status"] == "skipped_not_enabled"

    @pytest.mark.asyncio
    async def test_deliver_eod_digest_focus_mode(self, db_session, test_user):
        """Test skips EOD when user is in focus mode."""
        from app.db.models.focus import FocusModeState
        from app.db.models.triage import TriageUserSettings

        settings = TriageUserSettings(
            user_id=test_user.id,
            is_always_on=True,
        )
        db_session.add(settings)

        state = FocusModeState(
            user_id=test_user.id,
            is_active=True,
            mode="simple",
            started_at=datetime.utcnow(),
        )
        db_session.add(state)
        await db_session.commit()

        orchestrator = DigestDeliveryOrchestrator(db_session)
        result = await orchestrator.deliver_eod_digest(test_user.id)

        assert result["status"] == "skipped_focus_mode"

    @pytest.mark.asyncio
    async def test_custom_triggers(self, db_session):
        """Test orchestrator uses custom triggers when provided."""

        class CustomTrigger(DeliveryTriggerPlugin):
            @property
            def name(self) -> str:
                return "custom"

            async def check(self, user_id: str, db):
                return DeliveryTrigger(
                    trigger_type="custom",
                    user_id=user_id,
                    triggered_at=datetime.utcnow(),
                )

        orchestrator = DigestDeliveryOrchestrator(
            db_session,
            triggers=[CustomTrigger()],
        )

        result = await orchestrator.check_triggers("user-123")

        assert result is not None
        assert result.trigger_type == "custom"

