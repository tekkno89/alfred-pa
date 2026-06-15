"""Get the user's configuration and rules for a specific channel."""

import json
import logging
from typing import Any

from app.tools.base import BaseTool, ToolContext

logger = logging.getLogger(__name__)


class GetUserChannelRulesTool(BaseTool):
    name = "get_user_channel_rules"
    description = "Get the user's configuration and rules for a specific channel."
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
        user_id = context["user_id"]
        db = context["db"]

        try:
            from app.db.repositories.triage import MonitoredChannelRepository
            from app.services.triage_cache import TriageCacheService

            cache = TriageCacheService()

            # Try cache first
            cached = await cache.get_channel_rules(user_id, channel_id)
            if cached is not None:
                return json.dumps(cached)

            # Cache miss — query DB
            repo = MonitoredChannelRepository(db)
            channel = await repo.get_by_user_and_channel(user_id, channel_id)

            if channel is None:
                rules = {
                    "priority": "medium",
                    "triage_instructions": "",
                    "summary_behavior": "default",
                }
            else:
                rules = {
                    "priority": channel.priority or "medium",
                    "triage_instructions": channel.triage_instructions or "",
                    "summary_behavior": channel.summary_behavior or "default",
                }

            # Cache for next time
            await cache.set_channel_rules(user_id, channel_id, rules)

            return json.dumps(rules)
        except Exception as e:
            logger.error("GetUserChannelRulesTool error: %s", e)
            return json.dumps({"error": f"Failed to get channel rules: {e}"})
