"""Trigger a real digest delivery to test the full flow.

Run with:
    docker-compose -f docker-compose.dev.yml exec backend python scripts/trigger_digest.py [priority]

This will:
1. Create test triage classifications in the database
2. Enqueue the send_digest ARQ job
3. The worker will process it and send to Slack

Args:
    priority: p1, p2, or p3 (default: p1)
"""

import asyncio
import sys
from datetime import datetime
from uuid import uuid4

from sqlalchemy import select

from app.db.session import async_session_maker
from app.db.models import User
from app.db.models.triage import TriageClassification
from app.core.redis import get_redis
from arq.connections import ArqRedis


async def main(priority: str = "p1"):
    async with async_session_maker() as db:
        # Get user with Slack ID
        result = await db.execute(
            select(User).where(User.slack_user_id.isnot(None)).limit(1)
        )
        user = result.scalar_one_or_none()

        if not user:
            print("No user found in database. Please create a user first.")
            return

        if not user.slack_user_id:
            print("User has no slack_user_id. Cannot send digest.")
            return

        print(f"Using user: {user.email} (slack_id: {user.slack_user_id})")

        # Create test classifications
        now = datetime.utcnow()
        ts_base = int(now.timestamp())

        classifications = []

        # Thread conversation (3 messages)
        thread_ts = f"{ts_base}.000001"
        for i in range(3):
            msg = TriageClassification(
                id=str(uuid4()),
                user_id=user.id,
                sender_slack_id=f"U_sender_thread_{i}",
                sender_name=f"Thread User {i}",
                channel_id="C_THREAD_TEST",
                channel_name="test-thread-channel",
                message_ts=f"{ts_base}.{i + 1:06d}",
                thread_ts=thread_ts,
                priority_level=priority,
                confidence=0.9,
                classification_path="channel",
                abstract=f"Thread message {i + 1}: Discussion about project updates",
                queued_for_digest=True,
                created_at=now,
            )
            classifications.append(msg)
            db.add(msg)

        # DM conversation (2 messages)
        for i in range(2):
            msg = TriageClassification(
                id=str(uuid4()),
                user_id=user.id,
                sender_slack_id=f"U_dm_sender_{i}",
                sender_name=f"DM User {i}",
                channel_id="D_DM_TEST",
                channel_name=None,
                message_ts=f"{ts_base + 100}.{i + 1:06d}",
                thread_ts=None,
                priority_level=priority,
                confidence=0.85,
                classification_path="dm",
                abstract=f"DM message {i + 1}: Quick question about the meeting",
                queued_for_digest=True,
                created_at=now,
            )
            classifications.append(msg)
            db.add(msg)

        # Channel messages without thread
        for i in range(2):
            msg = TriageClassification(
                id=str(uuid4()),
                user_id=user.id,
                sender_slack_id=f"U_channel_sender_{i}",
                sender_name=f"Channel User {i}",
                channel_id="C_CHANNEL_TEST",
                channel_name="test-channel",
                message_ts=f"{ts_base + 200}.{i + 1:06d}",
                thread_ts=None,
                priority_level=priority,
                confidence=0.8,
                classification_path="channel",
                abstract=f"Channel message {i + 1}: FYI about the deployment",
                queued_for_digest=True,
                created_at=now,
            )
            classifications.append(msg)
            db.add(msg)

        await db.commit()
        print(
            f"\nCreated {len(classifications)} test classifications with priority {priority}"
        )

        # Enqueue the digest job
        redis_client = await get_redis()
        pool = ArqRedis(redis_client.connection_pool)

        job_id = (
            f"digest_{priority}_{user.id}_{datetime.utcnow().strftime('%Y%m%d_%H%M')}"
        )

        print(f"\nEnqueuing send_digest job: {job_id}")
        await pool.enqueue_job(
            "send_digest",
            user_id=user.id,
            priority=priority,
            digest_type="scheduled",
            use_conversation_grouping=True,
            _job_id=job_id,
        )

        print("\nJob enqueued! Check the worker logs to see it process:")
        print("  docker-compose -f docker-compose.dev.yml logs -f worker")
        print("\nThe digest should be sent to your Slack DM.")


if __name__ == "__main__":
    priority = sys.argv[1] if len(sys.argv) > 1 else "p1"
    if priority not in ("p1", "p2", "p3"):
        print(f"Invalid priority: {priority}. Must be p1, p2, or p3.")
        sys.exit(1)
    asyncio.run(main(priority))
