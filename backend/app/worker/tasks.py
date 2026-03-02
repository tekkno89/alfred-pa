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
    Send a Slack DM reminder for a todo that has reached its due time.
    """
    async with get_db_session() as db:
        from app.db.repositories import UserRepository
        from app.db.repositories.todo import TodoRepository

        todo_repo = TodoRepository(db)
        user_repo = UserRepository(db)

        todo = await todo_repo.get(todo_id)
        if not todo or todo.status != "open":
            logger.info(f"Todo {todo_id} not found or already completed, skipping reminder")
            return {"status": "skipped", "reason": "not_open"}

        user = await user_repo.get(user_id)
        if not user or not user.slack_user_id:
            logger.info(f"User {user_id} has no Slack ID, skipping reminder")
            return {"status": "skipped", "reason": "no_slack"}

        # Build and send Slack message
        try:
            import hashlib
            import hmac
            import time

            from app.core.config import get_settings
            from app.services.slack import get_slack_service

            settings = get_settings()
            slack_service = get_slack_service()

            # HMAC sign the todo_id for button verification
            timestamp = str(int(time.time()))
            payload_str = f"{todo_id}:{timestamp}"
            signature = hmac.new(
                settings.jwt_secret.encode(),
                payload_str.encode(),
                hashlib.sha256,
            ).hexdigest()[:16]
            signed_value = f"{payload_str}:{signature}"

            # Priority emoji
            priority_emoji = {0: ":red_circle:", 1: ":orange_circle:", 2: ":large_blue_circle:", 3: ":white_circle:"}
            p_emoji = priority_emoji.get(todo.priority, ":large_blue_circle:")
            p_label = {0: "P0 Urgent", 1: "P1 High", 2: "P2 Medium", 3: "P3 Low"}.get(todo.priority, "P2 Medium")

            # Build blocks
            text_parts = [f"{p_emoji} *{todo.title}*", f"Priority: {p_label}"]
            if todo.description:
                text_parts.append(todo.description)

            blocks = [
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": "\n".join(text_parts),
                    },
                },
                {
                    "type": "actions",
                    "elements": [
                        {
                            "type": "button",
                            "text": {"type": "plain_text", "text": "Mark Done"},
                            "style": "primary",
                            "action_id": "todo_complete",
                            "value": signed_value,
                        },
                        {
                            "type": "button",
                            "text": {"type": "plain_text", "text": "1 Hour"},
                            "action_id": "todo_snooze_1h",
                            "value": signed_value,
                        },
                        {
                            "type": "button",
                            "text": {"type": "plain_text", "text": "3 Hours"},
                            "action_id": "todo_snooze_3h",
                            "value": signed_value,
                        },
                        {
                            "type": "button",
                            "text": {"type": "plain_text", "text": "Tomorrow AM"},
                            "action_id": "todo_snooze_tomorrow",
                            "value": signed_value,
                        },
                    ],
                },
            ]

            fallback_text = f"Todo reminder: {todo.title} ({p_label})"

            await slack_service.client.chat_postMessage(
                channel=user.slack_user_id,
                text=fallback_text,
                blocks=blocks,
            )

            # Mark reminder as sent
            await todo_repo.update_todo(todo, reminder_sent_at=datetime.utcnow())
            await db.commit()

            logger.info(f"Sent todo reminder for todo {todo_id} to user {user_id}")
            return {"status": "sent", "todo_id": todo_id}

        except Exception as e:
            logger.error(f"Failed to send todo reminder for {todo_id}: {e}", exc_info=True)
            return {"status": "error", "error": str(e)}


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
