import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock
from app.services.active_hours_service import ActiveHoursService
from app.db.models.triage import ActiveHoursConfig, TriageUserSettings


@pytest.fixture
def mock_db():
    return AsyncMock()


@pytest.fixture
def service(mock_db):
    return ActiveHoursService(mock_db)


class TestIsWithinActiveHours:
    @pytest.mark.asyncio
    async def test_returns_true_when_no_config(self, service, mock_db):
        """No config means always active (24/7)."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute.return_value = mock_result

        result = await service.is_within_active_hours(user_id="user-123")

        assert result is True

    @pytest.mark.asyncio
    async def test_returns_true_during_active_hours(self, service, mock_db):
        """Returns True when current time is within configured window."""
        now = datetime(2024, 1, 1, 10, 0)  # Monday

        config = MagicMock(spec=ActiveHoursConfig)
        config.day_of_week = 0  # Monday
        config.start_time = "09:00"
        config.end_time = "18:00"
        config.is_enabled = True

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [config]
        mock_db.execute.return_value = mock_result

        result = await service.is_within_active_hours(user_id="user-123", now=now)

        assert result is True

    @pytest.mark.asyncio
    async def test_returns_false_outside_active_hours(self, service, mock_db):
        """Returns False when current time is outside window."""
        now = datetime(2024, 1, 1, 20, 0)  # Monday

        config = MagicMock(spec=ActiveHoursConfig)
        config.day_of_week = 0  # Monday
        config.start_time = "09:00"
        config.end_time = "18:00"
        config.is_enabled = True

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [config]
        mock_db.execute.return_value = mock_result

        result = await service.is_within_active_hours(user_id="user-123", now=now)

        assert result is False

    @pytest.mark.asyncio
    async def test_returns_true_on_disabled_day(self, service, mock_db):
        """Disabled day means always active (no restrictions)."""
        now = datetime(2024, 1, 6, 10, 0)  # Saturday

        config = MagicMock(spec=ActiveHoursConfig)
        config.day_of_week = 5  # Saturday
        config.start_time = "09:00"
        config.end_time = "18:00"
        config.is_enabled = False

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [config]
        mock_db.execute.return_value = mock_result

        result = await service.is_within_active_hours(user_id="user-123", now=now)

        assert result is True

    @pytest.mark.asyncio
    async def test_returns_true_when_no_config_for_day(self, service, mock_db):
        """Returns True when configs exist but not for current day."""
        now = datetime(2024, 1, 3, 10, 0)  # Wednesday (day 2)

        config = MagicMock(spec=ActiveHoursConfig)
        config.day_of_week = 0  # Monday
        config.start_time = "09:00"
        config.end_time = "18:00"
        config.is_enabled = True

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [config]
        mock_db.execute.return_value = mock_result

        result = await service.is_within_active_hours(user_id="user-123", now=now)

        assert result is True


class TestSetConfigs:
    @pytest.mark.asyncio
    async def test_set_configs_replaces_existing(self, service, mock_db):
        """set_configs should replace all existing configs."""
        existing = MagicMock(spec=ActiveHoursConfig)
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [existing]
        mock_db.execute.return_value = mock_result

        new_configs = [
            {"day_of_week": 0, "start_time": "09:00", "end_time": "17:00", "is_enabled": True},
            {"day_of_week": 1, "start_time": "09:00", "end_time": "17:00", "is_enabled": True},
        ]

        await service.set_configs(user_id="user-123", configs=new_configs)

        mock_db.delete.assert_called_once_with(existing)
        assert mock_db.add.call_count == 2
        mock_db.commit.assert_called_once()


class TestSetBreakthrough:
    @pytest.mark.asyncio
    async def test_set_breakthrough_updates_existing(self, service, mock_db):
        """set_breakthrough should update existing settings."""
        settings = MagicMock(spec=TriageUserSettings)
        mock_result = MagicMock()
        mock_result.scalars.return_value.first.return_value = settings
        mock_db.execute.return_value = mock_result

        await service.set_breakthrough(user_id="user-123", breakthrough="queue_all")

        assert settings.active_hours_breakthrough == "queue_all"
        mock_db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_set_breakthrough_creates_if_missing(self, service, mock_db):
        """set_breakthrough should create settings if none exist."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.first.return_value = None
        mock_db.execute.return_value = mock_result

        await service.set_breakthrough(user_id="user-123", breakthrough="allow_notify_now")

        mock_db.add.assert_called_once()
        mock_db.commit.assert_called_once()


class TestShouldDeliverNow:
    @pytest.mark.asyncio
    async def test_delivers_during_active_hours(self, service, mock_db):
        """Always delivers during active hours."""
        now = datetime(2024, 1, 1, 10, 0)  # Monday 10:00

        config = MagicMock(spec=ActiveHoursConfig)
        config.day_of_week = 0
        config.start_time = "09:00"
        config.end_time = "18:00"
        config.is_enabled = True

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [config]
        mock_db.execute.return_value = mock_result

        result = await service.should_deliver_now(
            user_id="user-123",
            action="notify_now",
            now=now,
        )

        assert result is True

    @pytest.mark.asyncio
    async def test_queues_outside_hours_with_allow_notify_now(self, service, mock_db):
        """Queues non-P0 outside hours when breakthrough is allow_notify_now."""
        now = datetime(2024, 1, 1, 20, 0)  # Monday 20:00

        config = MagicMock(spec=ActiveHoursConfig)
        config.day_of_week = 0
        config.start_time = "09:00"
        config.end_time = "18:00"
        config.is_enabled = True

        settings = MagicMock(spec=TriageUserSettings)
        settings.active_hours_breakthrough = "allow_notify_now"

        mock_config_result = MagicMock()
        mock_config_result.scalars.return_value.all.return_value = [config]

        mock_settings_result = MagicMock()
        mock_settings_result.scalars.return_value.first.return_value = settings

        mock_db.execute.side_effect = [mock_config_result, mock_settings_result]

        result = await service.should_deliver_now(
            user_id="user-123",
            action="summarize_next",
            now=now,
        )

        assert result is False

    @pytest.mark.asyncio
    async def test_notify_now_breaks_through_with_allow_notify_now(self, service, mock_db):
        """P0 breaks through outside hours when breakthrough is allow_notify_now."""
        now = datetime(2024, 1, 1, 20, 0)  # Monday 20:00

        config = MagicMock(spec=ActiveHoursConfig)
        config.day_of_week = 0
        config.start_time = "09:00"
        config.end_time = "18:00"
        config.is_enabled = True

        settings = MagicMock(spec=TriageUserSettings)
        settings.active_hours_breakthrough = "allow_notify_now"

        mock_config_result = MagicMock()
        mock_config_result.scalars.return_value.all.return_value = [config]

        mock_settings_result = MagicMock()
        mock_settings_result.scalars.return_value.first.return_value = settings

        mock_db.execute.side_effect = [mock_config_result, mock_settings_result]

        result = await service.should_deliver_now(
            user_id="user-123",
            action="notify_now",
            now=now,
        )

        assert result is True

    @pytest.mark.asyncio
    async def test_queues_all_with_queue_all(self, service, mock_db):
        """Queues everything outside hours when breakthrough is queue_all."""
        now = datetime(2024, 1, 1, 20, 0)  # Monday 20:00

        config = MagicMock(spec=ActiveHoursConfig)
        config.day_of_week = 0
        config.start_time = "09:00"
        config.end_time = "18:00"
        config.is_enabled = True

        settings = MagicMock(spec=TriageUserSettings)
        settings.active_hours_breakthrough = "queue_all"

        mock_config_result = MagicMock()
        mock_config_result.scalars.return_value.all.return_value = [config]

        mock_settings_result = MagicMock()
        mock_settings_result.scalars.return_value.first.return_value = settings

        mock_db.execute.side_effect = [mock_config_result, mock_settings_result]

        result = await service.should_deliver_now(
            user_id="user-123",
            action="notify_now",
            now=now,
        )

        assert result is False
