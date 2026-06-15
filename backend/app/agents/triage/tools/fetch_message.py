"""Fetch a single Slack message by channel + timestamp."""

import json
import logging
from typing import Any

from app.services.slack import get_slack_service
from app.tools.base import BaseTool, ToolContext

logger = logging.getLogger(__name__)


class FetchMessageTool(BaseTool):
    name = "fetch_message"
    description = (
        "Fetch a message's text from Slack. Call this FIRST before classifying."
    )
    parameters_schema: dict[str, Any] = {
        "type": "object",
        "properties": {
            "channel_id": {
                "type": "string",
                "description": "Slack channel ID",
            },
            "message_ts": {
                "type": "string",
                "description": "Message timestamp",
            },
        },
        "required": ["channel_id", "message_ts"],
    }
    max_iterations = 1

    async def execute(
        self, *, context: ToolContext | None = None, **kwargs: Any
    ) -> str:
        channel_id: str = kwargs["channel_id"]
        message_ts: str = kwargs["message_ts"]

        try:
            slack = get_slack_service()
            resp = await slack.client.conversations_history(
                channel=channel_id,
                oldest=message_ts,
                inclusive=True,
                limit=1,
            )
            messages = resp.get("messages", [])
            if not messages:
                return json.dumps({"error": "Message not found"})

            msg = messages[0]
            return json.dumps(
                {
                    "text": msg.get("text", ""),
                    "user": msg.get("user", ""),
                    "ts": msg.get("ts", ""),
                    "thread_ts": msg.get("thread_ts"),
                }
            )
        except Exception as e:
            logger.error("FetchMessageTool error: %s", e)
            return json.dumps({"error": f"Failed to fetch message: {e}"})
