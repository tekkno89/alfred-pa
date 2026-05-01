"""Migration script to create conversation_summaries for existing digests.

This script processes existing digest_summary records and creates
conversation_summary records for them by grouping their child messages.

Run with:
    cd backend && uv run python -m app.scripts.migrate_conversation_summaries
"""

import asyncio
import logging
from collections import defaultdict

from app.core.config import get_settings
from app.db.session import async_session_maker
from app.db.models.triage import TriageClassification
from app.db.models.conversation_summary import ConversationSummary
from app.db.repositories.conversation_summary import ConversationSummaryRepository
from sqlalchemy import select, update, func

logger = logging.getLogger(__name__)


async def migrate_digest(digest_id: str, user_id: str, db) -> int:
    """Migrate a single digest_summary to conversation_summaries.

    Returns the number of conversation_summaries created.
    """
    result = await db.execute(
        select(TriageClassification)
        .where(TriageClassification.digest_summary_id == digest_id)
        .where(TriageClassification.user_id == user_id)
        .order_by(TriageClassification.message_ts.asc())
    )
    children = list(result.scalars().all())

    if not children:
        return 0

    groups: dict[tuple[str, str | None], list[TriageClassification]] = defaultdict(list)

    for child in children:
        key = (child.channel_id, child.thread_ts)
        groups[key].append(child)

    repo = ConversationSummaryRepository(db)
    created = 0

    for (channel_id, thread_ts), msgs in groups.items():
        sorted_msgs = sorted(msgs, key=lambda m: m.message_ts)
        first_msg = sorted_msgs[0]
        last_msg = sorted_msgs[-1]

        priority_order = {"p0": 0, "p1": 1, "p2": 2, "p3": 3}
        highest = 3
        for m in sorted_msgs:
            p = priority_order.get(m.priority_level, 3)
            if p < highest:
                highest = p
        priority_level = ["p0", "p1", "p2", "p3"][highest]

        participants_data = []
        seen_ids = set()
        for m in sorted_msgs:
            if m.sender_slack_id not in seen_ids:
                seen_ids.add(m.sender_slack_id)
                participants_data.append({
                    "slack_id": m.sender_slack_id,
                    "name": m.sender_name,
                })

        conversation_type = "thread" if thread_ts else ("dm" if channel_id.startswith("D") else "channel")

        summary = ConversationSummary(
            user_id=user_id,
            conversation_type=conversation_type,
            channel_id=channel_id,
            channel_name=first_msg.channel_name,
            thread_ts=thread_ts,
            abstract=f"{len(sorted_msgs)} messages",
            participants=participants_data,
            message_count=len(sorted_msgs),
            priority_level=priority_level,
            first_message_ts=first_msg.message_ts,
            slack_permalink=first_msg.slack_permalink,
            digest_summary_id=digest_id,
            first_message_at=first_msg.created_at,
            last_message_at=last_msg.created_at,
        )

        summary = await repo.create(summary)
        created += 1

        await db.execute(
            update(TriageClassification)
            .where(TriageClassification.id.in_([m.id for m in sorted_msgs]))
            .values(conversation_summary_id=summary.id)
        )
        await db.flush()

    return created


async def run_migration(batch_size: int = 100) -> None:
    """Run the migration for all existing digest_summaries."""
    settings = get_settings()

    async with async_session_maker() as db:
        result = await db.execute(
            select(TriageClassification)
            .where(TriageClassification.priority_level == "digest_summary")
            .order_by(TriageClassification.created_at.asc())
        )
        digests = list(result.scalars().all())

        total = len(digests)
        logger.info(f"Found {total} digest_summaries to migrate")

        migrated = 0
        conversations_created = 0

        for i, digest in enumerate(digests):
            if i % 10 == 0:
                logger.info(f"Progress: {i}/{total} digests processed")

            created = await migrate_digest(digest.id, digest.user_id, db)
            migrated += 1
            conversations_created += created

            if migrated % batch_size == 0:
                await db.commit()
                logger.info(f"Committed batch at {migrated} digests")

        await db.commit()
        logger.info(f"Migration complete: {migrated} digests migrated, {conversations_created} conversations created")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_migration())
