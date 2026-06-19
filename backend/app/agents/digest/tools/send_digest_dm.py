"""Send the formatted digest to the user via Slack DM."""

import json
import logging
from typing import Any

from app.db.repositories.user import UserRepository
from app.services.slack import get_slack_service
from app.tools.base import BaseTool, ToolContext

logger = logging.getLogger(__name__)


class SendDigestDmTool(BaseTool):
    name = "send_digest_dm"
    description = "Send the formatted digest to the user via Slack DM."
    parameters_schema: dict[str, Any] = {
        "type": "object",
        "properties": {
            "digest_text": {
                "type": "string",
                "description": "Complete digest in Slack mrkdwn format",
            },
        },
        "required": ["digest_text"],
    }
    max_iterations = 1

    async def execute(
        self, *, context: ToolContext | None = None, **kwargs: Any
    ) -> str:
        if not context or "db" not in context or "user_id" not in context:
            return json.dumps({"error": "Missing context (db or user_id)"})

        digest_text: str = kwargs["digest_text"]

        try:
            db = context["db"]
            user_id = context["user_id"]

            user_repo = UserRepository(db)
            user = await user_repo.get(user_id)

            if not user:
                return json.dumps({"error": "User not found"})

            if not user.slack_user_id:
                return json.dumps({"error": "User has no linked Slack account"})

            slack = get_slack_service()
            await slack.send_message(
                channel=user.slack_user_id,
                text=digest_text,
            )

            return json.dumps({"status": "sent"})
        except Exception as e:
            logger.error("SendDigestDmTool error: %s", e)
            return json.dumps({"error": f"Failed to send digest DM: {e}"})
