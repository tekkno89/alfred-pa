"""Manual test script for digest flow.

Run with:
    docker-compose -f docker-compose.dev.yml exec backend python scripts/test_digest_flow.py

This will:
1. Create test triage classifications in the database
2. Run the conversation grouping
3. Show what would be in the digest
"""

import asyncio
from datetime import datetime
from uuid import uuid4

from sqlalchemy import select

from app.db.session import async_session_maker
from app.db.models import User
from app.db.models.triage import TriageClassification
from app.services.digest_grouper import DigestGrouper
from app.services.digest_response_checker import DigestResponseChecker


async def main():
    async with async_session_maker() as db:
        # Get or create a test user
        result = await db.execute(select(User).limit(1))
        user = result.scalar_one_or_none()

        if not user:
            print("No user found in database. Please create a user first.")
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
                priority_level="p1",
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
                priority_level="p1",
                confidence=0.85,
                classification_path="dm",
                abstract=f"DM message {i + 1}: Quick question about the meeting",
                queued_for_digest=True,
                created_at=now,
            )
            classifications.append(msg)
            db.add(msg)

        # Channel messages without thread (will be grouped by LLM)
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
                priority_level="p2",
                confidence=0.8,
                classification_path="channel",
                abstract=f"Channel message {i + 1}: FYI about the deployment",
                queued_for_digest=True,
                created_at=now,
            )
            classifications.append(msg)
            db.add(msg)

        # Message with user already reacted (should be filtered)
        reacted_msg = TriageClassification(
            id=str(uuid4()),
            user_id=user.id,
            sender_slack_id="U_reacted_sender",
            sender_name="Reacted Sender",
            channel_id="C_REACTED_TEST",
            channel_name="reacted-channel",
            message_ts=f"{ts_base + 300}.000001",
            thread_ts=None,
            priority_level="p1",
            confidence=0.9,
            classification_path="channel",
            abstract="User already reacted to this",
            queued_for_digest=True,
            user_reacted_at=now,
            created_at=now,
        )
        classifications.append(reacted_msg)
        db.add(reacted_msg)

        # Message with user already responded (should be filtered)
        responded_msg = TriageClassification(
            id=str(uuid4()),
            user_id=user.id,
            sender_slack_id="U_responded_sender",
            sender_name="Responded Sender",
            channel_id="C_RESPONDED_TEST",
            channel_name="responded-channel",
            message_ts=f"{ts_base + 400}.000001",
            thread_ts=None,
            priority_level="p1",
            confidence=0.9,
            classification_path="channel",
            abstract="User already responded to this",
            queued_for_digest=True,
            user_responded_at=now,
            created_at=now,
        )
        classifications.append(responded_msg)
        db.add(responded_msg)

        await db.commit()
        print(f"\nCreated {len(classifications)} test classifications")

        # Filter out already responded
        unresponded = [
            c
            for c in classifications
            if c.user_reacted_at is None and c.user_responded_at is None
        ]
        print(f"After filtering reacted/responded: {len(unresponded)} items")

        # Group into conversations
        grouper = DigestGrouper()
        conversations = grouper.group_messages(unresponded)

        print(f"\n=== Grouped into {len(conversations)} conversations ===\n")

        for i, conv in enumerate(conversations, 1):
            print(f"Conversation {i}: {conv.conversation_type.upper()}")
            print(f"  Channel: {conv.channel_id} ({conv.channel_name or 'DM'})")
            print(f"  Messages: {len(conv.messages)}")
            for msg in conv.messages:
                print(f"    - [{msg.sender_name}] {msg.abstract[:60]}...")
            print()

        # Check for user responses (this would call Slack API in production)
        print("=== Response Detection ===")
        print("(Skipping Slack API check in this test script)")

        # Show what would be in the final digest
        print(f"\n=== Final Digest ===")
        print(f"Total conversations to include: {len(conversations)}")

        for i, conv in enumerate(conversations, 1):
            summary = (
                conv.messages[0].abstract
                if len(conv.messages) == 1
                else f"{len(conv.messages)} messages"
            )
            print(
                f"  {i}. [{conv.conversation_type}] {conv.channel_name or conv.channel_id}: {summary[:50]}..."
            )

        # Clean up
        print("\n=== Cleaning up test data ===")
        for c in classifications:
            await db.delete(c)
        await db.commit()
        print("Done!")


if __name__ == "__main__":
    asyncio.run(main())
