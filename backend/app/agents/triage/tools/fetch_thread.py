"""Fetch thread replies for context."""

import json
import logging
from typing import Any

from app.tools.base import BaseTool, ToolContext

logger = logging.getLogger(__name__)


class FetchThreadTool(BaseTool):
    name = "fetch_thread"
    description = "Fetch thread messages for context."
    parameters_schema: dict[str, Any] = {
        "type": "object",
        "properties": {
            "channel_id": {
                "type": "string",
                "description": "Slack channel ID",
            },
            "thread_ts": {
                "type": "string",
                "description": "Thread parent timestamp",
            },
            "limit": {
                "type": "integer",
                "description": "Max messages to fetch (default 10)",
                "default": 10,
            },
        },
        "required": ["channel_id", "thread_ts"],
    }
    max_iterations = 2

    async def execute(
        self, *, context: ToolContext | None = None, **kwargs: Any
    ) -> str:
        channel_id: str = kwargs["channel_id"]
        thread_ts: str = kwargs["thread_ts"]
        limit: int = kwargs.get("limit", 10)

        try:
            from app.services.slack_channel_client import SlackChannelClient

            client = await SlackChannelClient.for_user(context["db"], context["user_id"])
            resp = await client.conversations_replies(
                channel=channel_id,
                ts=thread_ts,
                limit=limit,
            )
            messages = resp.get("messages", [])
            result = [
                {
                    "user": m.get("user", ""),
                    "text": m.get("text", ""),
                    "ts": m.get("ts", ""),
                }
                for m in messages
            ]
            return json.dumps({"messages": result, "count": len(result)})
        except Exception as e:
            logger.error("FetchThreadTool error: %s", e)
            return json.dumps({"error": f"Failed to fetch thread: {e}"})
