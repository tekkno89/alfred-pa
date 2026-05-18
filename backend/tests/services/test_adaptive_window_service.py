"""Unit tests for adaptive window service."""

import pytest
from datetime import datetime, UTC
from unittest.mock import AsyncMock, MagicMock

from app.services.adaptive_window_service import (
    AdaptiveWindowService,
    STARTER_WINDOWS,
    EMA_ALPHA,
    MIN_SAMPLES,
    MAX_SHIFT_FRACTION,
    WINDOW_FLOOR,
    WINDOW_CEILING,
)


class TestAdaptiveWindowService:
    """Tests for AdaptiveWindowService."""

    @pytest.fixture
    def mock_db(self):
        return AsyncMock()

    @pytest.fixture
    def service(self, mock_db):
        return AdaptiveWindowService(mock_db)

    def test_starter_windows_defined(self):
        """Test that all expected starter windows are defined."""
        expected_types = [
            "pr_review_request",
            "direct_question",
            "mention",
            "discussion_relevant",
            "announcement",
            "informational",
        ]
        for msg_type in expected_types:
            assert msg_type in STARTER_WINDOWS
            assert STARTER_WINDOWS[msg_type] >= WINDOW_FLOOR
            assert STARTER_WINDOWS[msg_type] <= WINDOW_CEILING

    @pytest.mark.asyncio
    async def test_get_window_returns_starter_if_no_window_exists(self, service, mock_db):
        """Test that get_window returns starter value when no learned window exists."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        window = await service.get_window("user-1", "pr_review_request")
        assert window == STARTER_WINDOWS["pr_review_request"]

    @pytest.mark.asyncio
    async def test_get_window_returns_starter_if_not_enough_samples(self, service, mock_db):
        """Test that get_window returns starter value if sample count is below minimum."""
        mock_window = MagicMock()
        mock_window.sample_count = MIN_SAMPLES - 1
        mock_window.window_minutes = 45

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_window
        mock_db.execute.return_value = mock_result

        window = await service.get_window("user-1", "pr_review_request")
        assert window == STARTER_WINDOWS["pr_review_request"]

    @pytest.mark.asyncio
    async def test_get_window_returns_learned_window(self, service, mock_db):
        """Test that get_window returns learned window when enough samples."""
        mock_window = MagicMock()
        mock_window.sample_count = MIN_SAMPLES
        mock_window.window_minutes = 25

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_window
        mock_db.execute.return_value = mock_result

        window = await service.get_window("user-1", "pr_review_request")
        assert window == 25

    @pytest.mark.asyncio
    async def test_record_engagement_creates_new_window(self, service, mock_db):
        """Test that record_engagement creates a new window if none exists."""
        from app.db.models.triage import MessageType, AdaptiveWindow

        mock_msg_type = MagicMock(spec=MessageType)
        mock_msg_type.id = "msg-type-1"
        mock_msg_type_result = MagicMock()
        mock_msg_type_result.scalar_one_or_none.return_value = mock_msg_type

        mock_window_result = MagicMock()
        mock_window_result.scalar_one_or_none.return_value = None

        mock_db.execute.side_effect = [mock_msg_type_result, mock_window_result]
        mock_db.flush = AsyncMock()

        result = await service.record_engagement("user-1", "pr_review_request", 20)

        assert mock_db.add.called
        assert mock_db.flush.called

    @pytest.mark.asyncio
    async def test_record_engagement_ema_calculation(self, service, mock_db):
        """Test EMA calculation in record_engagement."""
        from app.db.models.triage import MessageType

        mock_msg_type = MagicMock(spec=MessageType)
        mock_msg_type.id = "msg-type-1"
        mock_msg_type_result = MagicMock()
        mock_msg_type_result.scalar_one_or_none.return_value = mock_msg_type

        mock_window = MagicMock()
        mock_window.window_minutes = 30
        mock_window.sample_count = MIN_SAMPLES
        mock_window.message_type_id = "msg-type-1"

        mock_window_result = MagicMock()
        mock_window_result.scalar_one_or_none.return_value = mock_window

        mock_db.execute.side_effect = [mock_msg_type_result, mock_window_result]
        mock_db.flush = AsyncMock()

        actual_delay = 20
        expected_ema = int(EMA_ALPHA * actual_delay + (1 - EMA_ALPHA) * 30)

        await service.record_engagement("user-1", "pr_review_request", actual_delay)

        assert mock_window.window_minutes == expected_ema

    @pytest.mark.asyncio
    async def test_record_engagement_respects_max_shift(self, service, mock_db):
        """Test that record_engagement limits shifts to max percentage."""
        from app.db.models.triage import MessageType

        mock_msg_type = MagicMock(spec=MessageType)
        mock_msg_type.id = "msg-type-1"
        mock_msg_type_result = MagicMock()
        mock_msg_type_result.scalar_one_or_none.return_value = mock_msg_type

        mock_window = MagicMock()
        mock_window.window_minutes = 30
        mock_window.sample_count = MIN_SAMPLES
        mock_window.message_type_id = "msg-type-1"

        mock_window_result = MagicMock()
        mock_window_result.scalar_one_or_none.return_value = mock_window

        mock_db.execute.side_effect = [mock_msg_type_result, mock_window_result]
        mock_db.flush = AsyncMock()

        huge_delay = 1000
        max_shift = int(30 * MAX_SHIFT_FRACTION)
        expected_window = 30 + max_shift

        await service.record_engagement("user-1", "pr_review_request", huge_delay)

        assert mock_window.window_minutes == expected_window

    @pytest.mark.asyncio
    async def test_record_engagement_respects_floor(self, service, mock_db):
        """Test that record_engagement respects the floor value."""
        from app.db.models.triage import MessageType

        mock_msg_type = MagicMock(spec=MessageType)
        mock_msg_type.id = "msg-type-1"
        mock_msg_type_result = MagicMock()
        mock_msg_type_result.scalar_one_or_none.return_value = mock_msg_type

        mock_window = MagicMock()
        mock_window.window_minutes = 20
        mock_window.sample_count = MIN_SAMPLES
        mock_window.message_type_id = "msg-type-1"

        mock_window_result = MagicMock()
        mock_window_result.scalar_one_or_none.return_value = mock_window

        mock_db.execute.side_effect = [mock_msg_type_result, mock_window_result]
        mock_db.flush = AsyncMock()

        tiny_delay = 1

        await service.record_engagement("user-1", "pr_review_request", tiny_delay)

        assert mock_window.window_minutes >= WINDOW_FLOOR

    @pytest.mark.asyncio
    async def test_record_engagement_respects_ceiling(self, service, mock_db):
        """Test that record_engagement respects the ceiling value."""
        from app.db.models.triage import MessageType

        mock_msg_type = MagicMock(spec=MessageType)
        mock_msg_type.id = "msg-type-1"
        mock_msg_type_result = MagicMock()
        mock_msg_type_result.scalar_one_or_none.return_value = mock_msg_type

        mock_window = MagicMock()
        mock_window.window_minutes = 1400
        mock_window.sample_count = MIN_SAMPLES
        mock_window.message_type_id = "msg-type-1"

        mock_window_result = MagicMock()
        mock_window_result.scalar_one_or_none.return_value = mock_window

        mock_db.execute.side_effect = [mock_msg_type_result, mock_window_result]
        mock_db.flush = AsyncMock()

        huge_delay = 2000

        await service.record_engagement("user-1", "announcement", huge_delay)

        assert mock_window.window_minutes <= WINDOW_CEILING

    @pytest.mark.asyncio
    async def test_reset_window(self, service, mock_db):
        """Test that reset_window resets to starter value."""
        from app.db.models.triage import MessageType

        mock_msg_type = MagicMock(spec=MessageType)
        mock_msg_type.id = "msg-type-1"
        mock_msg_type_result = MagicMock()
        mock_msg_type_result.scalar_one_or_none.return_value = mock_msg_type

        mock_window = MagicMock()
        mock_window.window_minutes = 100
        mock_window.sample_count = 10

        mock_window_result = MagicMock()
        mock_window_result.scalar_one_or_none.return_value = mock_window

        mock_db.execute.side_effect = [mock_msg_type_result, mock_window_result]
        mock_db.flush = AsyncMock()

        result = await service.reset_window("user-1", "pr_review_request")

        assert result == STARTER_WINDOWS["pr_review_request"]
        assert mock_window.window_minutes == STARTER_WINDOWS["pr_review_request"]
        assert mock_window.sample_count == 0

    @pytest.mark.asyncio
    async def test_get_all_windows(self, service, mock_db):
        """Test get_all_windows returns list of windows."""
        from app.db.models.triage import MessageType, AdaptiveWindow

        mock_msg_type1 = MagicMock(spec=MessageType)
        mock_msg_type1.type_name = "pr_review_request"

        mock_msg_type2 = MagicMock(spec=MessageType)
        mock_msg_type2.type_name = "direct_question"

        mock_window1 = MagicMock(spec=AdaptiveWindow)
        mock_window1.window_minutes = 25
        mock_window1.sample_count = 10
        mock_window1.last_updated = datetime.now(UTC)

        mock_window2 = MagicMock(spec=AdaptiveWindow)
        mock_window2.window_minutes = 45
        mock_window2.sample_count = 3
        mock_window2.last_updated = datetime.now(UTC)

        mock_result = MagicMock()
        mock_result.all.return_value = [
            (mock_window1, mock_msg_type1),
            (mock_window2, mock_msg_type2),
        ]
        mock_db.execute.return_value = mock_result

        windows = await service.get_all_windows("user-1")

        assert len(windows) == 2
        assert windows[0]["message_type_name"] == "pr_review_request"
        assert windows[0]["is_learning"] == False
        assert windows[1]["message_type_name"] == "direct_question"
        assert windows[1]["is_learning"] == True
