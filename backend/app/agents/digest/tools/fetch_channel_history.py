"""Fetch recent messages from a Slack channel for digest context."""

import json
import logging
from typing import Any

from app.services.slack import get_slack_service
from app.tools.base import BaseTool, ToolContext

logger = logging.getLogger(__name__)


class DigestFetchChannelHistoryTool(BaseTool):
    name = "digest_fetch_channel_history"
    description = "Fetch recent messages from a channel for digest context."
    parameters_schema: dict[str, Any] = {
        "type": "object",
        "properties": {
            "channel_id": {
                "type": "string",
                "description": "Slack channel ID",
            },
            "limit": {
                "type": "integer",
                "description": "Max messages to fetch (default 10)",
                "default": 10,
            },
        },
        "required": ["channel_id"],
    }
    max_iterations = 2

    async def execute(
        self, *, context: ToolContext | None = None, **kwargs: Any
    ) -> str:
        channel_id: str = kwargs["channel_id"]
        limit: int = kwargs.get("limit", 10)

        try:
            slack = get_slack_service()
            resp = await slack.client.conversations_history(
                channel=channel_id,
                limit=limit,
            )
            messages = resp.get("messages", [])

            # Filter out thread replies (where thread_ts != ts)
            top_level = []
            for m in messages:
                ts = m.get("ts", "")
                thread_ts = m.get("thread_ts")
                # Keep if no thread_ts (top-level) or thread_ts == ts (thread parent)
                if thread_ts is None or thread_ts == ts:
                    top_level.append(
                        {
                            "user": m.get("user", ""),
                            "text": m.get("text", ""),
                            "ts": ts,
                            "thread_ts": thread_ts,
                        }
                    )

            return json.dumps({"messages": top_level, "count": len(top_level)})
        except Exception as e:
            logger.error("DigestFetchChannelHistoryTool error: %s", e)
            return json.dumps({"error": f"Failed to fetch channel history: {e}"})
