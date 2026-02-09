"""Focus mode service for managing focus sessions."""

import logging
from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.repositories import (
    FocusModeStateRepository,
    FocusSettingsRepository,
    FocusVIPListRepository,
)
from app.schemas.focus import FocusStatusResponse

logger = logging.getLogger(__name__)


class FocusModeService:
    """Service for managing focus mode."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.state_repo = FocusModeStateRepository(db)
        self.settings_repo = FocusSettingsRepository(db)
        self.vip_repo = FocusVIPListRepository(db)

    async def enable(
        self,
        user_id: str,
        duration_minutes: int | None = None,
        custom_message: str | None = None,
        previous_slack_status: dict | None = None,
    ) -> FocusStatusResponse:
        """
        Enable focus mode for a user.

        Args:
            user_id: The user's ID
            duration_minutes: Optional duration in minutes (auto-disable after)
            custom_message: Optional custom auto-reply message
            previous_slack_status: The user's Slack status before enabling focus mode

        Returns:
            Current focus status
        """
        state = await self.state_repo.get_or_create(user_id)

        now = datetime.utcnow()
        ends_at = None
        if duration_minutes:
            ends_at = now + timedelta(minutes=duration_minutes)

        # Get default message from settings if not provided
        if not custom_message:
            settings = await self.settings_repo.get_or_create(user_id)
            custom_message = settings.default_message

        await self.state_repo.update(
            state,
            is_active=True,
            mode="simple",
            started_at=now,
            ends_at=ends_at,
            custom_message=custom_message,
            previous_slack_status=previous_slack_status,
            pomodoro_phase=None,
            pomodoro_session_count=0,
        )

        return await self.get_status(user_id)

    async def disable(self, user_id: str) -> FocusStatusResponse:
        """
        Disable focus mode for a user.

        Args:
            user_id: The user's ID

        Returns:
            Current focus status
        """
        state = await self.state_repo.get_by_user_id(user_id)
        if state and state.is_active:
            await self.state_repo.update(
                state,
                is_active=False,
                ended_at=datetime.utcnow(),
            )

        return await self.get_status(user_id)

    async def get_status(self, user_id: str) -> FocusStatusResponse:
        """
        Get current focus status for a user.

        Args:
            user_id: The user's ID

        Returns:
            Current focus status
        """
        state = await self.state_repo.get_by_user_id(user_id)

        if not state:
            return FocusStatusResponse(is_active=False)

        # Check if session has expired
        if state.is_active and state.ends_at:
            now = datetime.utcnow()
            if state.ends_at <= now:
                # For pomodoro mode, don't auto-disable - let the worker handle
                # phase transitions. The ends_at is just the phase end time.
                if state.mode == "pomodoro":
                    # Phase has expired, but session continues
                    # Return current state with time_remaining = 0
                    pass
                else:
                    # Simple focus mode - disable it
                    await self.state_repo.update(
                        state,
                        is_active=False,
                        ended_at=now,
                    )
                    return FocusStatusResponse(is_active=False)

        # Calculate time remaining
        time_remaining = None
        if state.is_active and state.ends_at:
            remaining = state.ends_at - datetime.utcnow()
            time_remaining = max(0, int(remaining.total_seconds()))

        return FocusStatusResponse(
            is_active=state.is_active,
            mode=state.mode,
            started_at=state.started_at,
            ends_at=state.ends_at,
            custom_message=state.custom_message,
            pomodoro_phase=state.pomodoro_phase,
            pomodoro_session_count=state.pomodoro_session_count,
            pomodoro_total_sessions=state.pomodoro_total_sessions,
            pomodoro_work_minutes=state.pomodoro_work_minutes,
            pomodoro_break_minutes=state.pomodoro_break_minutes,
            time_remaining_seconds=time_remaining,
        )

    async def is_in_focus_mode(self, user_id: str) -> bool:
        """Check if user is currently in focus mode."""
        state = await self.state_repo.get_by_user_id(user_id)
        return state.is_active if state else False

    async def get_custom_message(self, user_id: str) -> str | None:
        """Get the custom focus message for a user."""
        state = await self.state_repo.get_by_user_id(user_id)
        return state.custom_message if state else None

    async def get_previous_slack_status(self, user_id: str) -> dict | None:
        """Get the saved previous Slack status for a user."""
        state = await self.state_repo.get_by_user_id(user_id)
        return state.previous_slack_status if state else None

    async def start_pomodoro(
        self,
        user_id: str,
        custom_message: str | None = None,
        previous_slack_status: dict | None = None,
        work_minutes: int | None = None,
        break_minutes: int | None = None,
        total_sessions: int | None = None,
    ) -> FocusStatusResponse:
        """
        Start pomodoro mode for a user.

        Args:
            user_id: The user's ID
            custom_message: Optional custom auto-reply message
            previous_slack_status: The user's Slack status before starting pomodoro
            work_minutes: Duration of work sessions (defaults to user settings)
            break_minutes: Duration of break sessions (defaults to user settings)
            total_sessions: Total number of sessions to complete

        Returns:
            Current focus status
        """
        state = await self.state_repo.get_or_create(user_id)
        settings = await self.settings_repo.get_or_create(user_id)

        # Use provided values or fall back to user settings
        actual_work_minutes = work_minutes or settings.pomodoro_work_minutes
        actual_break_minutes = break_minutes or settings.pomodoro_break_minutes

        now = datetime.utcnow()
        work_duration = timedelta(minutes=actual_work_minutes)

        if not custom_message:
            custom_message = settings.default_message

        await self.state_repo.update(
            state,
            is_active=True,
            mode="pomodoro",
            started_at=now,
            ends_at=now + work_duration,
            custom_message=custom_message,
            previous_slack_status=previous_slack_status,
            pomodoro_phase="work",
            pomodoro_session_count=1,
            pomodoro_total_sessions=total_sessions,
            pomodoro_work_minutes=actual_work_minutes,
            pomodoro_break_minutes=actual_break_minutes,
        )

        return await self.get_status(user_id)

    async def skip_pomodoro_phase(self, user_id: str) -> FocusStatusResponse:
        """
        Skip to the next pomodoro phase.

        Args:
            user_id: The user's ID

        Returns:
            Current focus status (is_active=False if all sessions complete)
        """
        state = await self.state_repo.get_by_user_id(user_id)
        if not state or not state.is_active or state.mode != "pomodoro":
            return await self.get_status(user_id)

        # Use per-session config, fall back to defaults
        work_minutes = state.pomodoro_work_minutes or 25
        break_minutes = state.pomodoro_break_minutes or 5
        total = state.pomodoro_total_sessions
        now = datetime.utcnow()

        if state.pomodoro_phase == "work":
            # Check if this was the last session (no break after final work)
            if total and state.pomodoro_session_count >= total:
                # All sessions complete, end pomodoro
                await self.state_repo.update(
                    state,
                    is_active=False,
                    ended_at=now,
                )
                return await self.get_status(user_id)

            # Not the last session, switch to break
            break_duration = timedelta(minutes=break_minutes)
            await self.state_repo.update(
                state,
                pomodoro_phase="break",
                ends_at=now + break_duration,
            )
        else:
            # Check if starting another work session would exceed limit
            if total and state.pomodoro_session_count >= total:
                # Already at max sessions, end pomodoro
                await self.state_repo.update(
                    state,
                    is_active=False,
                    ended_at=now,
                )
                return await self.get_status(user_id)

            # Switch to work
            work_duration = timedelta(minutes=work_minutes)
            await self.state_repo.update(
                state,
                pomodoro_phase="work",
                ends_at=now + work_duration,
                pomodoro_session_count=state.pomodoro_session_count + 1,
            )

        return await self.get_status(user_id)

    async def transition_pomodoro_phase(self, user_id: str) -> str | None:
        """
        Automatically transition pomodoro phase when timer ends.
        Called by background worker.

        Args:
            user_id: The user's ID

        Returns:
            New phase name or None if no transition needed
        """
        state = await self.state_repo.get_by_user_id(user_id)
        if not state or not state.is_active or state.mode != "pomodoro":
            return None

        # Use per-session config, fall back to defaults
        work_minutes = state.pomodoro_work_minutes or 25
        break_minutes = state.pomodoro_break_minutes or 5
        now = datetime.utcnow()

        if state.pomodoro_phase == "work":
            # Check if this was the last session (no break after final work)
            total = state.pomodoro_total_sessions
            if total and state.pomodoro_session_count >= total:
                # All sessions complete, end pomodoro
                await self.state_repo.update(
                    state,
                    is_active=False,
                    ended_at=now,
                )
                return None

            # Not the last session, switch to break
            break_duration = timedelta(minutes=break_minutes)
            await self.state_repo.update(
                state,
                pomodoro_phase="break",
                ends_at=now + break_duration,
            )
            return "break"
        else:
            # Switch from break to next work session
            work_duration = timedelta(minutes=work_minutes)
            await self.state_repo.update(
                state,
                pomodoro_phase="work",
                ends_at=now + work_duration,
                pomodoro_session_count=state.pomodoro_session_count + 1,
            )
            return "work"

    async def is_vip(self, user_id: str, sender_slack_id: str) -> bool:
        """Check if a Slack user is in the VIP list."""
        return await self.vip_repo.is_vip(user_id, sender_slack_id)


async def get_expired_focus_sessions(db: AsyncSession) -> list[str]:
    """Get user IDs of expired focus sessions. Called by background worker."""
    repo = FocusModeStateRepository(db)
    now = datetime.utcnow()
    expired = await repo.get_active_expired(now)
    return [state.user_id for state in expired]


async def expire_focus_session(db: AsyncSession, user_id: str) -> None:
    """Expire a focus session. Called by background worker."""
    service = FocusModeService(db)
    await service.disable(user_id)
