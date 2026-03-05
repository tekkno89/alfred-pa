"""Todo notification service -- dispatches todo events to Slack, SSE, and webhooks."""

import hashlib
import hmac
import json
import logging
import random
import time
from datetime import datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.redis import get_redis
from app.db.repositories import UserRepository
from app.db.repositories.todo import TodoRepository
from app.services.notifications import NotificationService

logger = logging.getLogger(__name__)

_REMINDER_INTROS = [
    "Hey, just a heads up — this task is due now:",
    "Friendly reminder, this one's due:",
    "This just came due on your list:",
    "Heads up — you've got something due:",
    "Quick nudge — this is due now:",
    "Don't forget, this one's ready for you:",
    "Looks like this task just came due:",
    "Hey — this one's due, whenever you're ready:",
    "Popping in to remind you about this:",
    "This is on your plate now:",
    "Just flagging this — it's due:",
    "Time's up on this one:",
]


class TodoNotificationService:
    """Dispatches todo notifications across all channels (Slack, SSE, webhooks)."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.todo_repo = TodoRepository(db)
        self.user_repo = UserRepository(db)
        self.notification_service = NotificationService(db)

    async def send_due_reminder(self, todo_id: str, user_id: str) -> dict[str, Any]:
        """
        Send a 'todo is due' notification to all channels.

        Args:
            todo_id: The todo's ID
            user_id: The user's ID

        Returns:
            dict with status and per-channel results
        """
        todo = await self.todo_repo.get(todo_id)
        if not todo or todo.status != "open":
            logger.info(f"Todo {todo_id} not found or already completed, skipping reminder")
            return {"status": "skipped", "reason": "not_open"}

        user = await self.user_repo.get(user_id)
        if not user:
            logger.info(f"User {user_id} not found, skipping reminder")
            return {"status": "skipped", "reason": "no_user"}

        results: dict[str, Any] = {}

        # Channel 1: Slack DM (if user has Slack linked)
        if user.slack_user_id:
            try:
                slack_result = await self._send_slack_reminder(todo, user)
                results["slack"] = slack_result
            except Exception as e:
                logger.error(f"Slack reminder failed for todo {todo_id}: {e}", exc_info=True)
                results["slack"] = {"error": str(e)}
        else:
            logger.info(f"User {user_id} has no Slack ID, skipping Slack notification")

        # Channel 2: SSE + Webhooks (via NotificationService)
        try:
            ns_result = await self.notification_service.publish(
                user_id,
                "todo_due",
                {
                    "todo_id": str(todo.id),
                    "title": todo.title,
                    "priority": todo.priority,
                    "description": todo.description,
                },
            )
            results["sse_webhooks"] = ns_result
        except Exception as e:
            logger.error(f"SSE/webhook notification failed for todo {todo_id}: {e}")
            results["sse_webhooks"] = {"error": str(e)}

        # Mark reminder as sent
        await self.todo_repo.update_todo(todo, reminder_sent_at=datetime.utcnow())

        logger.info(f"Sent todo reminder for todo {todo_id} to user {user_id}")
        return {"status": "sent", "todo_id": str(todo_id), "channels": results}

    async def _send_slack_reminder(self, todo, user) -> dict[str, Any]:
        """Send Slack reminder — new top-level DM or threaded re-fire."""
        from app.services.slack import get_slack_service

        settings = get_settings()
        slack_service = get_slack_service()

        existing_thread_ts = todo.slack_reminder_thread_ts
        existing_channel = todo.slack_reminder_channel

        if existing_thread_ts and existing_channel:
            # Re-fire after snooze: post text-only in the existing thread
            return await self._refire_in_thread(
                todo, slack_service, existing_channel, existing_thread_ts
            )

        # First-time reminder: send new top-level DM with buttons
        return await self._send_new_reminder(todo, user, slack_service, settings)

    async def _send_new_reminder(
        self, todo, user, slack_service, settings
    ) -> dict[str, Any]:
        """Send a new top-level DM with Mark Done / Snooze buttons."""
        # HMAC sign the todo_id for button verification
        timestamp = str(int(time.time()))
        payload_str = f"{todo.id}:{timestamp}"
        signature = hmac.new(
            settings.jwt_secret.encode(),
            payload_str.encode(),
            hashlib.sha256,
        ).hexdigest()[:16]
        signed_value = f"{payload_str}:{signature}"

        # Priority label
        p_label = {0: "P0 Urgent", 1: "P1 High", 2: "P2 Medium", 3: "P3 Low"}.get(
            todo.priority, "P2 Medium"
        )

        # Top-level message: natural intro + todo details + link
        intro = random.choice(_REMINDER_INTROS)
        todo_url = f"{settings.frontend_url}/todos"

        text_parts = [f"{intro}\n", f"*{todo.title}*", f"Priority: {p_label}"]
        if todo.description:
            text_parts.append(todo.description)
        text_parts.append(f"\n<{todo_url}|View in Alfred>")

        main_blocks = [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "\n".join(text_parts),
                },
            },
        ]

        fallback_text = f"Todo reminder: {todo.title} ({p_label})"

        # Send the top-level DM
        main_resp = await slack_service.client.chat_postMessage(
            channel=user.slack_user_id,
            text=fallback_text,
            blocks=main_blocks,
            metadata={
                "event_type": "alfred_todo_reminder",
                "event_payload": {"todo_id": str(todo.id)},
            },
        )
        main_ts = main_resp["ts"]
        dm_channel = main_resp["channel"]

        # Threaded reply: Mark Done + Snooze buttons
        action_blocks = [
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
                        "text": {"type": "plain_text", "text": "Snooze"},
                        "action_id": "todo_snooze",
                        "value": signed_value,
                    },
                ],
            },
        ]

        await slack_service.client.chat_postMessage(
            channel=dm_channel,
            text="Quick actions:",
            blocks=action_blocks,
            thread_ts=main_ts,
        )

        # Persist thread location on the todo for future re-fires
        await self.todo_repo.update_todo(
            todo,
            slack_reminder_thread_ts=main_ts,
            slack_reminder_channel=dm_channel,
        )

        # Store thread→todo mapping in Redis
        try:
            redis_client = await get_redis()
            thread_todo_key = f"thread_todo:{dm_channel}:{main_ts}"
            await redis_client.set(
                thread_todo_key,
                json.dumps({"todo_id": str(todo.id), "title": todo.title}),
                ex=7 * 86400,  # 7 days TTL
            )
        except Exception as e:
            logger.warning(f"Failed to store thread→todo mapping: {e}")

        return {"channel": dm_channel, "ts": main_ts}

    async def _refire_in_thread(
        self, todo, slack_service, channel: str, thread_ts: str
    ) -> dict[str, Any]:
        """Post a text-only reminder in the existing thread (no buttons)."""
        intro = random.choice(_REMINDER_INTROS)
        text = f"{intro}\n*{todo.title}*"

        await slack_service.client.chat_postMessage(
            channel=channel,
            text=text,
            thread_ts=thread_ts,
        )

        # Refresh the Redis thread→todo mapping so user replies still resolve
        try:
            redis_client = await get_redis()
            thread_todo_key = f"thread_todo:{channel}:{thread_ts}"
            await redis_client.set(
                thread_todo_key,
                json.dumps({"todo_id": str(todo.id), "title": todo.title}),
                ex=7 * 86400,
            )
        except Exception as e:
            logger.warning(f"Failed to refresh thread→todo mapping: {e}")

        return {"channel": channel, "ts": thread_ts, "refire": True}
