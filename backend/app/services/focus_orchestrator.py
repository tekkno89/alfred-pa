"""Focus mode orchestrator — shared logic for API routes, tools, and workers.

Composes FocusModeService, SlackUserService, NotificationService, and
scheduler functions into cohesive operations that keep Slack status, DND,
notifications, and background jobs in sync.
"""

import logging
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.repositories import FocusSettingsRepository
from app.schemas.focus import FocusStatusResponse
from app.services.focus import FocusModeService
from app.services.notifications import NotificationService
from app.services.slack_user import SlackUserService
from app.worker.scheduler import (
    cancel_focus_expiration,
    cancel_pomodoro_transition,
    schedule_focus_expiration,
    schedule_pomodoro_transition,
)

logger = logging.getLogger(__name__)


class FocusModeOrchestrator:
    """Orchestrates focus mode operations across services."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.focus_service = FocusModeService(db)
        self.slack_user_service = SlackUserService(db)
        self.notification_service = NotificationService(db)
        self.settings_repo = FocusSettingsRepository(db)

    # ------------------------------------------------------------------
    # Public operations
    # ------------------------------------------------------------------

    async def enable(
        self,
        user_id: str,
        duration_minutes: int | None = None,
        custom_message: str | None = None,
    ) -> FocusStatusResponse:
        """Enable simple focus mode with full Slack + notification flow."""
        # Save current Slack status before enabling
        previous_status = await self.slack_user_service.get_status(user_id)

        result = await self.focus_service.enable(
            user_id=user_id,
            duration_minutes=duration_minutes,
            custom_message=custom_message,
            previous_slack_status=previous_status,
        )

        # Set Slack status from user settings
        settings = await self.settings_repo.get_or_create(user_id)
        await self.slack_user_service.set_status(
            user_id,
            text=settings.slack_status_text or "In focus mode",
            emoji=settings.slack_status_emoji or ":no_bell:",
        )

        # Enable DND
        dnd_duration = duration_minutes or 480
        await self.slack_user_service.enable_dnd(user_id, dnd_duration)

        # Commit before publishing events so other sessions (e.g. SSE-triggered
        # refetches) can see the updated state immediately.
        await self.db.commit()

        # Publish event
        await self.notification_service.publish(
            user_id,
            "focus_started",
            {
                "mode": "simple",
                "duration_minutes": duration_minutes,
                "custom_message": custom_message,
            },
        )

        # Schedule expiration if duration is set
        if result.ends_at:
            await schedule_focus_expiration(user_id, result.ends_at)

        return result

    async def disable(self, user_id: str) -> FocusStatusResponse:
        """Disable focus mode with full Slack restore + notification flow."""
        # Cancel scheduled jobs
        await cancel_focus_expiration(user_id)
        await cancel_pomodoro_transition(user_id)

        # Get previous status before disabling
        previous_status = await self.focus_service.get_previous_slack_status(user_id)

        result = await self.focus_service.disable(user_id)

        # Restore Slack status
        await self._restore_slack_status(user_id, previous_status)

        # Disable DND
        await self.slack_user_service.disable_dnd(user_id)

        await self.db.commit()

        # Publish event
        await self.notification_service.publish(user_id, "focus_ended", {})

        return result

    async def get_status(self, user_id: str) -> FocusStatusResponse:
        """Get status with auto-expire side effects (Slack restore if expired)."""
        previous_status = await self.focus_service.get_previous_slack_status(user_id)
        was_active = await self.focus_service.is_in_focus_mode(user_id)

        result = await self.focus_service.get_status(user_id)

        # If session was active but now expired, clean up Slack
        if was_active and not result.is_active:
            await self._restore_slack_status(user_id, previous_status)
            await self.slack_user_service.disable_dnd(user_id)
            await self.db.commit()
            await self.notification_service.publish(
                user_id, "focus_ended", {"reason": "expired"}
            )

        return result

    async def start_pomodoro(
        self,
        user_id: str,
        custom_message: str | None = None,
        work_minutes: int | None = None,
        break_minutes: int | None = None,
        total_sessions: int | None = None,
    ) -> FocusStatusResponse:
        """Start pomodoro mode with full Slack + notification flow."""
        # Save current Slack status
        previous_status = await self.slack_user_service.get_status(user_id)

        result = await self.focus_service.start_pomodoro(
            user_id=user_id,
            custom_message=custom_message,
            previous_slack_status=previous_status,
            work_minutes=work_minutes,
            break_minutes=break_minutes,
            total_sessions=total_sessions,
        )

        # Set Slack status for work phase
        settings = await self.settings_repo.get_or_create(user_id)
        await self.slack_user_service.set_status(
            user_id,
            text=settings.pomodoro_work_status_text or "Pomodoro - Focus time",
            emoji=settings.pomodoro_work_status_emoji or ":tomato:",
        )

        # Enable DND for work phase
        work_mins = work_minutes or 25
        await self.slack_user_service.enable_dnd(user_id, work_mins)

        await self.db.commit()

        # Publish event
        await self.notification_service.publish(
            user_id,
            "pomodoro_work_started",
            {"session_count": result.pomodoro_session_count},
        )

        # Schedule phase transition
        if result.ends_at:
            await schedule_pomodoro_transition(user_id, result.ends_at)

        return result

    async def skip_pomodoro_phase(self, user_id: str) -> FocusStatusResponse:
        """Skip current pomodoro phase with Slack status update."""
        previous_status = await self.focus_service.get_previous_slack_status(user_id)

        # Cancel current transition job
        await cancel_pomodoro_transition(user_id)

        result = await self.focus_service.skip_pomodoro_phase(user_id)

        if not result.is_active:
            # Pomodoro ended — restore Slack and notify
            await self._restore_slack_status(user_id, previous_status)
            await self.slack_user_service.disable_dnd(user_id)
            await self.db.commit()
            await self.notification_service.publish(
                user_id, "pomodoro_complete", {}
            )
            return result

        await self.db.commit()

        # Update Slack status for new phase
        await self._set_pomodoro_phase_status(user_id, result)

        # Schedule next transition
        if result.ends_at:
            await schedule_pomodoro_transition(user_id, result.ends_at)

        return result

    async def transition_pomodoro_phase(self, user_id: str) -> dict[str, Any]:
        """Worker-triggered automatic phase transition."""
        new_phase = await self.focus_service.transition_pomodoro_phase(user_id)

        if new_phase is None:
            # Pomodoro ended
            previous_status = await self.focus_service.get_previous_slack_status(user_id)
            try:
                await self._restore_slack_status(user_id, previous_status)
            except Exception as e:
                logger.error(f"Error restoring Slack status for {user_id}: {e}")

            try:
                await self.slack_user_service.disable_dnd(user_id)
            except Exception as e:
                logger.error(f"Error disabling Slack DND for {user_id}: {e}")

            await self.db.commit()
            await self.notification_service.publish(
                user_id, "pomodoro_complete", {}
            )
            return {"status": "complete", "user_id": user_id}

        await self.db.commit()

        # Update Slack status for new phase
        settings = await self.settings_repo.get_or_create(user_id)
        try:
            if new_phase == "work":
                await self.slack_user_service.set_status(
                    user_id,
                    text=settings.pomodoro_work_status_text or "Pomodoro - Focus time",
                    emoji=settings.pomodoro_work_status_emoji or ":tomato:",
                )
                await self.notification_service.publish(
                    user_id, "pomodoro_work_started", {}
                )
            else:
                await self.slack_user_service.set_status(
                    user_id,
                    text=settings.pomodoro_break_status_text or "Pomodoro - Break time",
                    emoji=settings.pomodoro_break_status_emoji or ":coffee:",
                )
                await self.notification_service.publish(
                    user_id, "pomodoro_break_started", {}
                )
        except Exception as e:
            logger.error(f"Error updating Slack status for {user_id}: {e}")

        # Schedule next transition
        status = await self.focus_service.get_status(user_id)
        if status.is_active and status.ends_at:
            await schedule_pomodoro_transition(user_id, status.ends_at)

        return {"status": "transitioned", "user_id": user_id, "new_phase": new_phase}

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    async def _restore_slack_status(
        self, user_id: str, previous_status: dict | None
    ) -> None:
        """Restore Slack status to whatever it was before focus mode."""
        if previous_status:
            await self.slack_user_service.set_status(
                user_id,
                text=previous_status.get("text", ""),
                emoji=previous_status.get("emoji", ""),
            )
        else:
            await self.slack_user_service.set_status(
                user_id, text="", emoji=""
            )

    async def _set_pomodoro_phase_status(
        self, user_id: str, result: FocusStatusResponse
    ) -> None:
        """Set Slack status based on current pomodoro phase."""
        settings = await self.settings_repo.get_or_create(user_id)
        if result.pomodoro_phase == "work":
            await self.slack_user_service.set_status(
                user_id,
                text=settings.pomodoro_work_status_text or "Pomodoro - Focus time",
                emoji=settings.pomodoro_work_status_emoji or ":tomato:",
            )
            await self.notification_service.publish(
                user_id,
                "pomodoro_work_started",
                {"session_count": result.pomodoro_session_count},
            )
        else:
            await self.slack_user_service.set_status(
                user_id,
                text=settings.pomodoro_break_status_text or "Pomodoro - Break time",
                emoji=settings.pomodoro_break_status_emoji or ":coffee:",
            )
            await self.notification_service.publish(
                user_id,
                "pomodoro_break_started",
                {"session_count": result.pomodoro_session_count},
            )
