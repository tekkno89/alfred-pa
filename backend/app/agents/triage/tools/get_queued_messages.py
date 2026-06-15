"""Get messages already queued for digest for a user in a channel."""

import json
import logging
from typing import Any

from app.tools.base import BaseTool, ToolContext

logger = logging.getLogger(__name__)


class GetQueuedMessagesTool(BaseTool):
    name = "get_queued_messages"
    description = (
        "Get messages already queued for digest for this user in this channel. "
        "Call this SECOND."
    )
    parameters_schema: dict[str, Any] = {
        "type": "object",
        "properties": {
            "channel_id": {
                "type": "string",
                "description": "Slack channel ID",
            },
        },
        "required": ["channel_id"],
    }
    max_iterations = 1

    async def execute(
        self, *, context: ToolContext | None = None, **kwargs: Any
    ) -> str:
        if not context or not context.get("db") or not context.get("user_id"):
            return json.dumps({"error": "Missing db or user_id in context"})

        channel_id: str = kwargs["channel_id"]
        db = context["db"]
        user_id = context["user_id"]

        try:
            from app.db.repositories.triage import TriageClassificationRepository

            repo = TriageClassificationRepository(db)
            items = await repo.get_recent(
                user_id=user_id,
                channel_id=channel_id,
                action=["notify_now", "summarize_next", "summarize_eod", "ignore"],
                limit=10,
            )
            # Filter to only queued items
            queued = [i for i in items if i.queued_for_digest]

            messages = [
                {
                    "id": item.id,
                    "sender_name": item.sender_name,
                    "abstract": item.abstract,
                    "action": item.action,
                    "group_id": item.group_id,
                    "message_ts": item.message_ts,
                    "channel_name": item.channel_name,
                }
                for item in queued
            ]
            return json.dumps({"messages": messages, "count": len(messages)})
        except Exception as e:
            logger.error("GetQueuedMessagesTool error: %s", e)
            return json.dumps({"error": f"Failed to get queued messages: {e}"})
