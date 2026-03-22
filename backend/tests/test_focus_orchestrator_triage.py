"""Tests for triage hooks in FocusModeOrchestrator."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.focus_orchestrator import FocusModeOrchestrator


@pytest.fixture
def mock_db():
    return AsyncMock()


def _make_orchestrator(mock_db, **overrides):
    """Create an orchestrator with mocked dependencies."""
    with patch.object(FocusModeOrchestrator, "__init__", lambda self, db: None):
        orch = FocusModeOrchestrator.__new__(FocusModeOrchestrator)
        orch.db = mock_db
        orch.focus_service = overrides.get("focus_service", AsyncMock())
        orch.slack_user_service = overrides.get("slack_user_service", AsyncMock())
        orch.notification_service = overrides.get("notification_service", AsyncMock())
        orch.settings_repo = overrides.get("settings_repo", AsyncMock())
        orch.state_repo = overrides.get("state_repo", AsyncMock())
        orch.triage_delivery = overrides.get("triage_delivery", AsyncMock())
        return orch


class TestDisableTriageIntegration:
    async def test_sends_digest_on_disable(self, mock_db):
        """Disabling focus should send a triage digest for the session."""
        focus_state = MagicMock(id="session-1", is_active=True, started_at="2024-01-01T00:00:00")
        state_repo = AsyncMock()
        state_repo.get_by_user_id.return_value = focus_state

        focus_service = AsyncMock()
        focus_service.get_previous_slack_status.return_value = None
        focus_service.disable.return_value = MagicMock(is_active=False)

        triage_delivery = AsyncMock()

        with (
            patch("app.services.focus_orchestrator.cancel_focus_expiration"),
            patch("app.services.focus_orchestrator.cancel_pomodoro_transition"),
        ):
            orch = _make_orchestrator(
                mock_db,
                focus_service=focus_service,
                state_repo=state_repo,
                triage_delivery=triage_delivery,
            )
            await orch.disable("user-1")

        triage_delivery.generate_and_send_digest.assert_called_once_with(
            "user-1", "session-1", "2024-01-01T00:00:00"
        )

    async def test_disable_skips_digest_when_no_active_session(self, mock_db):
        """Should not send digest when there's no active focus session."""
        state_repo = AsyncMock()
        state_repo.get_by_user_id.return_value = None

        focus_service = AsyncMock()
        focus_service.get_previous_slack_status.return_value = None
        focus_service.disable.return_value = MagicMock(is_active=False)

        triage_delivery = AsyncMock()

        with (
            patch("app.services.focus_orchestrator.cancel_focus_expiration"),
            patch("app.services.focus_orchestrator.cancel_pomodoro_transition"),
        ):
            orch = _make_orchestrator(
                mock_db,
                focus_service=focus_service,
                state_repo=state_repo,
                triage_delivery=triage_delivery,
            )
            await orch.disable("user-1")

        triage_delivery.generate_and_send_digest.assert_not_called()

    async def test_disable_handles_digest_error_gracefully(self, mock_db):
        """Digest error should not prevent focus mode from disabling."""
        focus_state = MagicMock(id="session-1", is_active=True, started_at="2024-01-01T00:00:00")
        state_repo = AsyncMock()
        state_repo.get_by_user_id.return_value = focus_state

        focus_service = AsyncMock()
        focus_service.get_previous_slack_status.return_value = None
        focus_service.disable.return_value = MagicMock(is_active=False)

        triage_delivery = AsyncMock()
        triage_delivery.generate_and_send_digest.side_effect = Exception("Slack error")

        with (
            patch("app.services.focus_orchestrator.cancel_focus_expiration"),
            patch("app.services.focus_orchestrator.cancel_pomodoro_transition"),
        ):
            orch = _make_orchestrator(
                mock_db,
                focus_service=focus_service,
                state_repo=state_repo,
                triage_delivery=triage_delivery,
            )
            # Should not raise
            result = await orch.disable("user-1")

        assert result.is_active is False
        mock_db.commit.assert_called_once()


class TestTransitionPomodoroTriageIntegration:
    async def test_break_delivers_session_digest(self, mock_db):
        """Transitioning to break should deliver session digest."""
        focus_state = MagicMock(id="session-1", is_active=True, started_at="2024-01-01T00:00:00")
        state_repo = AsyncMock()
        state_repo.get_by_user_id.return_value = focus_state

        focus_service = AsyncMock()
        focus_service.transition_pomodoro_phase.return_value = "break"
        focus_service.get_status.return_value = MagicMock(
            is_active=True, ends_at=None
        )

        triage_delivery = AsyncMock()

        orch = _make_orchestrator(
            mock_db,
            focus_service=focus_service,
            state_repo=state_repo,
            triage_delivery=triage_delivery,
        )
        result = await orch.transition_pomodoro_phase("user-1")

        triage_delivery.deliver_session_digest.assert_called_once_with(
            "user-1", "session-1", "2024-01-01T00:00:00"
        )
        assert result["new_phase"] == "break"

    async def test_work_clears_break_notification(self, mock_db):
        """Transitioning to work should clear break notification."""
        focus_state = MagicMock(id="session-1", is_active=True, started_at="2024-01-01T00:00:00")
        state_repo = AsyncMock()
        state_repo.get_by_user_id.return_value = focus_state

        focus_service = AsyncMock()
        focus_service.transition_pomodoro_phase.return_value = "work"
        focus_service.get_status.return_value = MagicMock(
            is_active=True, ends_at=None
        )

        triage_delivery = AsyncMock()

        orch = _make_orchestrator(
            mock_db,
            focus_service=focus_service,
            state_repo=state_repo,
            triage_delivery=triage_delivery,
        )
        result = await orch.transition_pomodoro_phase("user-1")

        triage_delivery.clear_break_notification.assert_called_once_with("user-1")
        assert result["new_phase"] == "work"

    async def test_complete_sends_digest(self, mock_db):
        """Pomodoro completion should send triage digest."""
        focus_state = MagicMock(id="session-1", is_active=True, started_at="2024-01-01T00:00:00")
        state_repo = AsyncMock()
        state_repo.get_by_user_id.return_value = focus_state

        focus_service = AsyncMock()
        focus_service.transition_pomodoro_phase.return_value = None
        focus_service.get_previous_slack_status.return_value = None

        triage_delivery = AsyncMock()

        orch = _make_orchestrator(
            mock_db,
            focus_service=focus_service,
            state_repo=state_repo,
            triage_delivery=triage_delivery,
        )
        result = await orch.transition_pomodoro_phase("user-1")

        triage_delivery.generate_and_send_digest.assert_called_once_with(
            "user-1", "session-1", "2024-01-01T00:00:00"
        )
        assert result["status"] == "complete"

    async def test_break_delivery_error_does_not_break_transition(self, mock_db):
        """Error delivering session digest should not prevent phase transition."""
        focus_state = MagicMock(id="session-1", is_active=True, started_at="2024-01-01T00:00:00")
        state_repo = AsyncMock()
        state_repo.get_by_user_id.return_value = focus_state

        focus_service = AsyncMock()
        focus_service.transition_pomodoro_phase.return_value = "break"
        focus_service.get_status.return_value = MagicMock(
            is_active=True, ends_at=None
        )

        triage_delivery = AsyncMock()
        triage_delivery.deliver_session_digest.side_effect = Exception("Redis error")

        orch = _make_orchestrator(
            mock_db,
            focus_service=focus_service,
            state_repo=state_repo,
            triage_delivery=triage_delivery,
        )
        # Should not raise
        result = await orch.transition_pomodoro_phase("user-1")

        assert result["status"] == "transitioned"
        assert result["new_phase"] == "break"
