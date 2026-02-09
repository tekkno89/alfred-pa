"""Background tasks for the ARQ worker."""

import logging
from datetime import datetime
from contextlib import asynccontextmanager

from app.db.session import async_session_maker
from app.db.repositories import FocusModeStateRepository
from app.services.focus import FocusModeService
from app.services.slack_user import SlackUserService
from app.services.notifications import NotificationService

logger = logging.getLogger(__name__)


@asynccontextmanager
async def get_db_session():
    """Get a database session with proper commit/rollback handling."""
    async with async_session_maker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def expire_focus_session(ctx: dict, user_id: str | None = None) -> dict:
    """
    Expire focus sessions that have passed their end time.

    Can be called with a specific user_id (scheduled job) or without
    to check all users (cron job).
    """
    async with get_db_session() as db:
        state_repo = FocusModeStateRepository(db)

        if user_id:
            # Specific user - scheduled expiration
            logger.info(f"Checking focus expiration for user {user_id}")
            state = await state_repo.get_by_user_id(user_id)

            if not state or not state.is_active:
                logger.info(f"User {user_id} focus session already inactive")
                return {"status": "already_inactive", "user_id": user_id}

            if state.ends_at and state.ends_at <= datetime.utcnow():
                await _expire_session(db, user_id, state)
                await db.commit()
                return {"status": "expired", "user_id": user_id}
            else:
                logger.info(f"User {user_id} focus session not yet expired")
                return {"status": "not_expired", "user_id": user_id}
        else:
            # Cron job - check all active sessions
            logger.info("Running focus expiration cron job")
            now = datetime.utcnow()
            expired_states = await state_repo.get_active_expired(now)

            expired_count = 0
            for state in expired_states:
                try:
                    await _expire_session(db, state.user_id, state)
                    expired_count += 1
                except Exception as e:
                    logger.error(f"Error expiring session for {state.user_id}: {e}")

            await db.commit()
            logger.info(f"Expired {expired_count} focus sessions")
            return {"status": "cron_complete", "expired_count": expired_count}


async def _expire_session(db, user_id: str, state) -> None:
    """Helper to expire a single session and restore Slack status."""
    focus_service = FocusModeService(db)
    slack_user_service = SlackUserService(db)
    notification_service = NotificationService(db)

    # Get previous status before disabling
    previous_status = state.previous_slack_status

    # Disable focus mode
    await focus_service.disable(user_id)

    # Restore Slack status
    try:
        if previous_status:
            await slack_user_service.set_status(
                user_id,
                text=previous_status.get("text", ""),
                emoji=previous_status.get("emoji", ""),
            )
        else:
            await slack_user_service.set_status(
                user_id,
                text="",
                emoji="",
            )
    except Exception as e:
        logger.error(f"Error restoring Slack status for {user_id}: {e}")

    # Disable Slack DND
    try:
        await slack_user_service.disable_dnd(user_id)
    except Exception as e:
        logger.error(f"Error disabling Slack DND for {user_id}: {e}")

    # Publish notification
    await notification_service.publish(
        user_id,
        "focus_ended",
        {"reason": "expired"},
    )

    logger.info(f"Expired focus session for user {user_id}")


async def transition_pomodoro(ctx: dict, user_id: str) -> dict:
    """
    Transition pomodoro to the next phase (work -> break or break -> work).
    Called when a pomodoro phase timer ends.
    """
    async with get_db_session() as db:
        focus_service = FocusModeService(db)
        slack_user_service = SlackUserService(db)
        notification_service = NotificationService(db)

        logger.info(f"Transitioning pomodoro phase for user {user_id}")

        new_phase = await focus_service.transition_pomodoro_phase(user_id)

        if new_phase is None:
            # Pomodoro ended (all sessions complete or not in pomodoro mode)
            # Restore Slack status
            previous_status = await focus_service.get_previous_slack_status(user_id)
            try:
                if previous_status:
                    await slack_user_service.set_status(
                        user_id,
                        text=previous_status.get("text", ""),
                        emoji=previous_status.get("emoji", ""),
                    )
                else:
                    await slack_user_service.set_status(
                        user_id,
                        text="",
                        emoji="",
                    )
            except Exception as e:
                logger.error(f"Error restoring Slack status for {user_id}: {e}")

            # Disable Slack DND
            try:
                await slack_user_service.disable_dnd(user_id)
            except Exception as e:
                logger.error(f"Error disabling Slack DND for {user_id}: {e}")

            await notification_service.publish(
                user_id,
                "pomodoro_complete",
                {},
            )
            return {"status": "complete", "user_id": user_id}

        # Update Slack status for new phase
        try:
            if new_phase == "work":
                await slack_user_service.set_status(
                    user_id,
                    text="Pomodoro - Focus time",
                    emoji=":tomato:",
                )
                await notification_service.publish(
                    user_id,
                    "pomodoro_work_started",
                    {},
                )
            else:
                await slack_user_service.set_status(
                    user_id,
                    text="Pomodoro - Break time",
                    emoji=":coffee:",
                )
                await notification_service.publish(
                    user_id,
                    "pomodoro_break_started",
                    {},
                )
        except Exception as e:
            logger.error(f"Error updating Slack status for {user_id}: {e}")

        # Schedule next transition
        status = await focus_service.get_status(user_id)
        if status.is_active and status.ends_at:
            from app.worker.scheduler import schedule_pomodoro_transition
            await schedule_pomodoro_transition(user_id, status.ends_at)

        return {"status": "transitioned", "user_id": user_id, "new_phase": new_phase}
