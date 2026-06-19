"""Save the digest record to the database for UI display."""

import json
import logging
from typing import Any

from sqlalchemy import update

from app.db.models.triage import TriageClassification
from app.db.repositories.triage import TriageClassificationRepository
from app.tools.base import BaseTool, ToolContext

logger = logging.getLogger(__name__)


class SaveDigestRecordTool(BaseTool):
    name = "save_digest_record"
    description = "Save the digest record to the database for UI display."
    parameters_schema: dict[str, Any] = {
        "type": "object",
        "properties": {
            "summary_text": {
                "type": "string",
                "description": "The digest summary text",
            },
            "message_ids": {
                "type": "array",
                "items": {"type": "string"},
                "description": "IDs of classified messages included in the digest",
            },
            "digest_type": {
                "type": "string",
                "enum": ["p1", "eod"],
                "description": "Type of digest: p1 (urgent) or eod (end-of-day)",
            },
        },
        "required": ["summary_text", "message_ids", "digest_type"],
    }
    max_iterations = 1

    async def execute(
        self, *, context: ToolContext | None = None, **kwargs: Any
    ) -> str:
        if not context or "db" not in context or "user_id" not in context:
            return json.dumps({"error": "Missing context (db or user_id)"})

        summary_text: str = kwargs["summary_text"]
        message_ids: list[str] = kwargs["message_ids"]
        digest_type: str = kwargs["digest_type"]

        try:
            db = context["db"]
            user_id = context["user_id"]

            # Map digest_type to action
            action = "summarize_next" if digest_type == "p1" else "summarize_eod"

            # Create consolidated digest record
            repo = TriageClassificationRepository(db)
            record = TriageClassification(
                user_id=user_id,
                sender_slack_id="system",
                channel_id="digest",
                message_ts="0",
                classification_path="channel",
                is_consolidated=True,
                action=action,
                abstract=summary_text,
                child_count=len(message_ids),
                digest_type="scheduled",
                queued_for_digest=False,
            )
            record = await repo.create(record)

            # Link child messages by setting their digest_summary_id
            if message_ids:
                stmt = (
                    update(TriageClassification)
                    .where(TriageClassification.id.in_(message_ids))
                    .values(digest_summary_id=record.id)
                )
                await db.execute(stmt)

            return json.dumps({
                "status": "saved",
                "digest_record_id": str(record.id),
            })
        except Exception as e:
            logger.error("SaveDigestRecordTool error: %s", e)
            return json.dumps({"error": f"Failed to save digest record: {e}"})
