"""Mark messages as delivered after digest is sent."""

import json
import logging
from typing import Any

from sqlalchemy import update

from app.db.models.triage import TriageClassification
from app.tools.base import BaseTool, ToolContext

logger = logging.getLogger(__name__)


class MarkDeliveredTool(BaseTool):
    name = "mark_delivered"
    description = "Mark messages as delivered after digest is sent."
    parameters_schema: dict[str, Any] = {
        "type": "object",
        "properties": {
            "message_ids": {
                "type": "array",
                "items": {"type": "string"},
                "description": "IDs of classified messages to mark as delivered",
            },
        },
        "required": ["message_ids"],
    }
    max_iterations = 1

    async def execute(
        self, *, context: ToolContext | None = None, **kwargs: Any
    ) -> str:
        if not context or "db" not in context:
            return json.dumps({"error": "Missing context (db)"})

        message_ids: list[str] = kwargs["message_ids"]

        try:
            db = context["db"]

            stmt = (
                update(TriageClassification)
                .where(TriageClassification.id.in_(message_ids))
                .values(
                    queued_for_digest=False,
                    processed_reason="summarized",
                )
            )
            result = await db.execute(stmt)

            return json.dumps({
                "status": "marked",
                "count": result.rowcount,
            })
        except Exception as e:
            logger.error("MarkDeliveredTool error: %s", e)
            return json.dumps({"error": f"Failed to mark delivered: {e}"})
