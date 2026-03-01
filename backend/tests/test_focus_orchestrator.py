"""Tests for FocusModeOrchestrator."""

import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from app.schemas.focus import FocusStatusResponse
from app.services.focus_orchestrator import FocusModeOrchestrator


@pytest.fixture
def mock_db():
    return AsyncMock()


@pytest.fixture
def orchestrator(mock_db):
    with patch.object(FocusModeOrchestrator, "__init__", lambda self, db: None):
        orch = FocusModeOrchestrator.__new__(FocusModeOrchestrator)
        orch.db = mock_db
        orch.focus_service = AsyncMock()
        orch.slack_user_service = AsyncMock()
        orch.notification_service = AsyncMock()
        orch.settings_repo = AsyncMock()
        return orch


class TestEnable:
    """Tests for orchestrator.enable()."""

    async def test_enable_without_duration(self, orchestrator):
        """Should enable focus mode, set Slack status, enable DND, publish event."""
        orchestrator.slack_user_service.get_status.return_value = {
            "text": "Available",
            "emoji": ":wave:",
        }
        status_result = FocusStatusResponse(
            is_active=True, mode="simple", ends_at=None
        )
        orchestrator.focus_service.enable.return_value = status_result

        settings = MagicMock()
        settings.slack_status_text = "Focusing"
        settings.slack_status_emoji = ":no_bell:"
        orchestrator.settings_repo.get_or_create.return_value = settings

        result = await orchestrator.enable("user-1")

        assert result.is_active is True
        orchestrator.focus_service.enable.assert_called_once_with(
            user_id="user-1",
            duration_minutes=None,
            custom_message=None,
            previous_slack_status={"text": "Available", "emoji": ":wave:"},
        )
        orchestrator.slack_user_service.set_status.assert_called_once_with(
            "user-1", text="Focusing", emoji=":no_bell:"
        )
        # Default DND duration when no duration set
        orchestrator.slack_user_service.enable_dnd.assert_called_once_with("user-1", 480)
        orchestrator.notification_service.publish.assert_called_once()

    async def test_enable_with_duration_schedules_expiration(self, orchestrator):
        """Should schedule expiration job when duration is set."""
        orchestrator.slack_user_service.get_status.return_value = None
        ends_at = datetime.utcnow() + timedelta(minutes=30)
        status_result = FocusStatusResponse(
            is_active=True, mode="simple", ends_at=ends_at
        )
        orchestrator.focus_service.enable.return_value = status_result

        settings = MagicMock()
        settings.slack_status_text = None
        settings.slack_status_emoji = None
        orchestrator.settings_repo.get_or_create.return_value = settings

        with patch(
            "app.services.focus_orchestrator.schedule_focus_expiration",
            new_callable=AsyncMock,
        ) as mock_schedule:
            result = await orchestrator.enable("user-1", duration_minutes=30)

            assert result.is_active is True
            mock_schedule.assert_called_once_with("user-1", ends_at)
            orchestrator.slack_user_service.enable_dnd.assert_called_once_with(
                "user-1", 30
            )


class TestDisable:
    """Tests for orchestrator.disable()."""

    async def test_disable_restores_slack_status(self, orchestrator):
        """Should cancel jobs, restore Slack status, disable DND, publish event."""
        orchestrator.focus_service.get_previous_slack_status.return_value = {
            "text": "Available",
            "emoji": ":wave:",
        }
        orchestrator.focus_service.disable.return_value = FocusStatusResponse(
            is_active=False
        )

        with patch(
            "app.services.focus_orchestrator.cancel_focus_expiration",
            new_callable=AsyncMock,
        ) as mock_cancel_exp, patch(
            "app.services.focus_orchestrator.cancel_pomodoro_transition",
            new_callable=AsyncMock,
        ) as mock_cancel_pom:
            result = await orchestrator.disable("user-1")

            assert result.is_active is False
            mock_cancel_exp.assert_called_once_with("user-1")
            mock_cancel_pom.assert_called_once_with("user-1")
            orchestrator.slack_user_service.set_status.assert_called_once_with(
                "user-1", text="Available", emoji=":wave:"
            )
            orchestrator.slack_user_service.disable_dnd.assert_called_once_with(
                "user-1"
            )
            orchestrator.notification_service.publish.assert_called_once_with(
                "user-1", "focus_ended", {}
            )

    async def test_disable_clears_status_when_no_previous(self, orchestrator):
        """Should clear Slack status when no previous status was saved."""
        orchestrator.focus_service.get_previous_slack_status.return_value = None
        orchestrator.focus_service.disable.return_value = FocusStatusResponse(
            is_active=False
        )

        with patch(
            "app.services.focus_orchestrator.cancel_focus_expiration",
            new_callable=AsyncMock,
        ), patch(
            "app.services.focus_orchestrator.cancel_pomodoro_transition",
            new_callable=AsyncMock,
        ):
            await orchestrator.disable("user-1")
            orchestrator.slack_user_service.set_status.assert_called_once_with(
                "user-1", text="", emoji=""
            )


class TestGetStatus:
    """Tests for orchestrator.get_status()."""

    async def test_status_active(self, orchestrator):
        """Should return active status without side effects."""
        orchestrator.focus_service.get_previous_slack_status.return_value = None
        orchestrator.focus_service.is_in_focus_mode.return_value = True
        orchestrator.focus_service.get_status.return_value = FocusStatusResponse(
            is_active=True, mode="simple"
        )

        result = await orchestrator.get_status("user-1")

        assert result.is_active is True
        # No Slack restore since still active
        orchestrator.slack_user_service.set_status.assert_not_called()

    async def test_status_expired_restores_slack(self, orchestrator):
        """Should restore Slack status when session expired during status check."""
        orchestrator.focus_service.get_previous_slack_status.return_value = {
            "text": "Old status",
            "emoji": ":ok:",
        }
        orchestrator.focus_service.is_in_focus_mode.return_value = True
        orchestrator.focus_service.get_status.return_value = FocusStatusResponse(
            is_active=False
        )

        result = await orchestrator.get_status("user-1")

        assert result.is_active is False
        orchestrator.slack_user_service.set_status.assert_called_once_with(
            "user-1", text="Old status", emoji=":ok:"
        )
        orchestrator.slack_user_service.disable_dnd.assert_called_once_with("user-1")
        orchestrator.notification_service.publish.assert_called_once_with(
            "user-1", "focus_ended", {"reason": "expired"}
        )


class TestStartPomodoro:
    """Tests for orchestrator.start_pomodoro()."""

    async def test_start_pomodoro(self, orchestrator):
        """Should start pomodoro with Slack status and DND."""
        orchestrator.slack_user_service.get_status.return_value = None
        ends_at = datetime.utcnow() + timedelta(minutes=25)
        orchestrator.focus_service.start_pomodoro.return_value = FocusStatusResponse(
            is_active=True,
            mode="pomodoro",
            pomodoro_phase="work",
            pomodoro_session_count=1,
            ends_at=ends_at,
        )

        settings = MagicMock()
        settings.pomodoro_work_status_text = "Deep work"
        settings.pomodoro_work_status_emoji = ":tomato:"
        orchestrator.settings_repo.get_or_create.return_value = settings

        with patch(
            "app.services.focus_orchestrator.schedule_pomodoro_transition",
            new_callable=AsyncMock,
        ) as mock_schedule:
            result = await orchestrator.start_pomodoro("user-1", work_minutes=25)

            assert result.is_active is True
            assert result.pomodoro_phase == "work"
            orchestrator.slack_user_service.set_status.assert_called_once_with(
                "user-1", text="Deep work", emoji=":tomato:"
            )
            orchestrator.slack_user_service.enable_dnd.assert_called_once_with(
                "user-1", 25
            )
            mock_schedule.assert_called_once_with("user-1", ends_at)


class TestSkipPomodoroPhase:
    """Tests for orchestrator.skip_pomodoro_phase()."""

    async def test_skip_to_break(self, orchestrator):
        """Should skip to break phase and update Slack status."""
        orchestrator.focus_service.get_previous_slack_status.return_value = None
        ends_at = datetime.utcnow() + timedelta(minutes=5)
        orchestrator.focus_service.skip_pomodoro_phase.return_value = FocusStatusResponse(
            is_active=True,
            mode="pomodoro",
            pomodoro_phase="break",
            pomodoro_session_count=1,
            ends_at=ends_at,
        )

        settings = MagicMock()
        settings.pomodoro_break_status_text = "Break time"
        settings.pomodoro_break_status_emoji = ":coffee:"
        orchestrator.settings_repo.get_or_create.return_value = settings

        with patch(
            "app.services.focus_orchestrator.cancel_pomodoro_transition",
            new_callable=AsyncMock,
        ), patch(
            "app.services.focus_orchestrator.schedule_pomodoro_transition",
            new_callable=AsyncMock,
        ) as mock_schedule:
            result = await orchestrator.skip_pomodoro_phase("user-1")

            assert result.pomodoro_phase == "break"
            mock_schedule.assert_called_once_with("user-1", ends_at)

    async def test_skip_ends_pomodoro(self, orchestrator):
        """Should restore Slack when all sessions complete."""
        orchestrator.focus_service.get_previous_slack_status.return_value = {
            "text": "Back",
            "emoji": ":wave:",
        }
        orchestrator.focus_service.skip_pomodoro_phase.return_value = FocusStatusResponse(
            is_active=False
        )

        with patch(
            "app.services.focus_orchestrator.cancel_pomodoro_transition",
            new_callable=AsyncMock,
        ):
            result = await orchestrator.skip_pomodoro_phase("user-1")

            assert result.is_active is False
            orchestrator.slack_user_service.set_status.assert_called_once_with(
                "user-1", text="Back", emoji=":wave:"
            )
            orchestrator.slack_user_service.disable_dnd.assert_called_once()
            orchestrator.notification_service.publish.assert_called_once_with(
                "user-1", "pomodoro_complete", {}
            )


class TestTransitionPomodoroPhase:
    """Tests for orchestrator.transition_pomodoro_phase()."""

    async def test_transition_to_break(self, orchestrator):
        """Should transition to break with status update and schedule next."""
        orchestrator.focus_service.transition_pomodoro_phase.return_value = "break"

        settings = MagicMock()
        settings.pomodoro_break_status_text = "On break"
        settings.pomodoro_break_status_emoji = ":coffee:"
        orchestrator.settings_repo.get_or_create.return_value = settings

        ends_at = datetime.utcnow() + timedelta(minutes=5)
        orchestrator.focus_service.get_status.return_value = FocusStatusResponse(
            is_active=True, ends_at=ends_at
        )

        with patch(
            "app.services.focus_orchestrator.schedule_pomodoro_transition",
            new_callable=AsyncMock,
        ) as mock_schedule:
            result = await orchestrator.transition_pomodoro_phase("user-1")

            assert result["status"] == "transitioned"
            assert result["new_phase"] == "break"
            orchestrator.slack_user_service.set_status.assert_called_once_with(
                "user-1", text="On break", emoji=":coffee:"
            )
            mock_schedule.assert_called_once_with("user-1", ends_at)

    async def test_transition_complete(self, orchestrator):
        """Should restore Slack when pomodoro is complete."""
        orchestrator.focus_service.transition_pomodoro_phase.return_value = None
        orchestrator.focus_service.get_previous_slack_status.return_value = {
            "text": "Done",
            "emoji": ":check:",
        }

        result = await orchestrator.transition_pomodoro_phase("user-1")

        assert result["status"] == "complete"
        orchestrator.slack_user_service.set_status.assert_called_once_with(
            "user-1", text="Done", emoji=":check:"
        )
        orchestrator.slack_user_service.disable_dnd.assert_called_once_with("user-1")
        orchestrator.notification_service.publish.assert_called_once_with(
            "user-1", "pomodoro_complete", {}
        )
