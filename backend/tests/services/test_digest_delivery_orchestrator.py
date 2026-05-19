"""Tests for digest_delivery_orchestrator service."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from app.services.digest_delivery_orchestrator import (
    DigestDeliveryOrchestrator,
    DeliveryTriggerPlugin,
)
from app.services.active_hours_service import ActiveHoursService


@pytest.fixture
def mock_db():
    return AsyncMock()


@pytest.fixture
def mock_active_hours_service():
    service = MagicMock(spec=ActiveHoursService)
    service.is_within_active_hours = AsyncMock(return_value=True)
    return service


class TestShouldDeliverDigest:
    """Tests for DigestDeliveryOrchestrator.should_deliver_digest."""

    @pytest.mark.asyncio
    async def test_returns_false_outside_active_hours(
        self, mock_db, mock_active_hours_service
    ):
        """Returns False when outside active hours."""
        orchestrator = DigestDeliveryOrchestrator(mock_db)
        orchestrator.active_hours_service = mock_active_hours_service
        mock_active_hours_service.is_within_active_hours.return_value = False

        result = await orchestrator.should_deliver_digest(user_id="user-123")

        assert result is False

    @pytest.mark.asyncio
    async def test_returns_true_when_trigger_fires(
        self, mock_db, mock_active_hours_service
    ):
        """Returns True when inside active hours and trigger fires."""
        orchestrator = DigestDeliveryOrchestrator(mock_db)
        orchestrator.active_hours_service = mock_active_hours_service

        mock_trigger = MagicMock(spec=DeliveryTriggerPlugin)
        mock_trigger.check = AsyncMock(return_value=MagicMock())
        orchestrator.triggers = [mock_trigger]

        result = await orchestrator.should_deliver_digest(user_id="user-123")

        assert result is True

    @pytest.mark.asyncio
    async def test_returns_false_when_no_triggers_fire(
        self, mock_db, mock_active_hours_service
    ):
        """Returns False when inside active hours but no triggers fire."""
        orchestrator = DigestDeliveryOrchestrator(mock_db)
        orchestrator.active_hours_service = mock_active_hours_service

        mock_trigger = MagicMock(spec=DeliveryTriggerPlugin)
        mock_trigger.check = AsyncMock(return_value=None)
        orchestrator.triggers = [mock_trigger]

        result = await orchestrator.should_deliver_digest(user_id="user-123")

        assert result is False

    @pytest.mark.asyncio
    async def test_continues_on_trigger_exception(
        self, mock_db, mock_active_hours_service
    ):
        """Continues checking other triggers when one raises an exception."""
        orchestrator = DigestDeliveryOrchestrator(mock_db)
        orchestrator.active_hours_service = mock_active_hours_service

        bad_trigger = MagicMock(spec=DeliveryTriggerPlugin)
        bad_trigger.name = "bad_trigger"
        bad_trigger.check = AsyncMock(side_effect=RuntimeError("trigger failed"))

        good_trigger = MagicMock(spec=DeliveryTriggerPlugin)
        good_trigger.name = "good_trigger"
        good_trigger.check = AsyncMock(return_value=MagicMock())

        orchestrator.triggers = [bad_trigger, good_trigger]

        result = await orchestrator.should_deliver_digest(user_id="user-123")

        assert result is True
