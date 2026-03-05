"""Background tasks for the ARQ worker."""

import logging
from datetime import datetime
from contextlib import asynccontextmanager

from app.db.session import async_session_maker
from app.db.repositories import FocusModeStateRepository

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

            # Skip pomodoro sessions - they should be handled by transition jobs
            if state.mode == "pomodoro":
                logger.info(f"Skipping pomodoro session expiration for user {user_id}")
                return {"status": "skipped_pomodoro", "user_id": user_id}

            if state.ends_at and state.ends_at <= datetime.utcnow():
                from app.services.focus_orchestrator import FocusModeOrchestrator

                orchestrator = FocusModeOrchestrator(db)
                await orchestrator.disable(user_id)
                await db.commit()
                logger.info(f"Expired focus session for user {user_id}")
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
                # Skip pomodoro sessions - they should be handled by transition jobs
                if state.mode == "pomodoro":
                    logger.info(f"Skipping pomodoro session for user {state.user_id}")
                    continue
                try:
                    from app.services.focus_orchestrator import FocusModeOrchestrator

                    orchestrator = FocusModeOrchestrator(db)
                    await orchestrator.disable(state.user_id)
                    expired_count += 1
                except Exception as e:
                    logger.error(f"Error expiring session for {state.user_id}: {e}")

            await db.commit()
            logger.info(f"Expired {expired_count} focus sessions")
            return {"status": "cron_complete", "expired_count": expired_count}


async def send_todo_reminder(ctx: dict, todo_id: str, user_id: str) -> dict:
    """
    Send notifications for a todo that has reached its due time.

    Dispatches to all configured channels (Slack, SSE, webhooks) via
    TodoNotificationService.
    """
    # Acquire a Redis lock to prevent duplicate notifications
    # (race between scheduled job and cron backup job)
    from app.core.redis import get_redis

    redis_client = await get_redis()
    lock_key = f"todo_reminder_lock:{todo_id}"
    acquired = await redis_client.set(lock_key, "1", nx=True, ex=300)  # 5-min TTL
    if not acquired:
        logger.info(f"Todo {todo_id} reminder already in progress, skipping (dedup)")
        return {"status": "skipped", "reason": "dedup_lock"}

    async with get_db_session() as db:
        from app.services.todo_notifications import TodoNotificationService

        service = TodoNotificationService(db)
        result = await service.send_due_reminder(todo_id, user_id)
        await db.commit()
        logger.info(f"Todo reminder result for {todo_id}: {result.get('status')}")
        return result


async def check_due_todo_reminders(ctx: dict) -> dict:
    """
    Cron backup: find todos past due with no reminder sent and send reminders.
    """
    async with get_db_session() as db:
        from app.db.repositories.todo import TodoRepository

        todo_repo = TodoRepository(db)
        now = datetime.utcnow()
        due_todos = await todo_repo.get_due_reminders(now)

        sent_count = 0
        for todo in due_todos:
            try:
                result = await send_todo_reminder(ctx, todo.id, todo.user_id)
                if result.get("status") == "sent":
                    sent_count += 1
            except Exception as e:
                logger.error(f"Error sending reminder for todo {todo.id}: {e}")

        logger.info(f"Cron: sent {sent_count} todo reminders")
        return {"status": "cron_complete", "sent_count": sent_count}


async def transition_pomodoro(ctx: dict, user_id: str) -> dict:
    """
    Transition pomodoro to the next phase (work -> break or break -> work).
    Called when a pomodoro phase timer ends.
    """
    async with get_db_session() as db:
        from app.services.focus_orchestrator import FocusModeOrchestrator

        logger.info(f"Transitioning pomodoro phase for user {user_id}")
        orchestrator = FocusModeOrchestrator(db)
        return await orchestrator.transition_pomodoro_phase(user_id)
