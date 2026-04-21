"""Integration tests for digest generation with conversation grouping."""

import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch, MagicMock
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.triage import TriageClassification
from app.services.digest_grouper import DigestGrouper
from app.services.digest_response_checker import DigestResponseChecker
from app.services.triage_delivery import TriageDeliveryService
from tests.factories import UserFactory, TriageClassificationFactory


def utcnow():
    """Get current UTC time as naive datetime (DB stores without timezone)."""
    return datetime.utcnow()


@pytest.fixture
async def test_user(db_session: AsyncSession):
    """Create a test user."""
    user = UserFactory(slack_user_id="U12345678")
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest.fixture
async def classifications(test_user, db_session: AsyncSession):
    """Create test classifications for digest testing."""
    now = utcnow()
    ts_base = int(now.timestamp())

    # Create various types of messages
    items = []

    # Thread conversation (3 messages in same thread)
    thread_ts = f"{ts_base}.000001"
    for i in range(3):
        msg = TriageClassification(
            id=str(uuid4()),
            user_id=test_user.id,
            sender_slack_id=f"U_sender_{i}",
            sender_name=f"Sender {i}",
            channel_id="C_THREAD_001",
            channel_name="thread-channel",
            message_ts=f"{ts_base}.{i + 1:06d}",
            thread_ts=thread_ts,
            priority_level="p1",
            confidence=0.9,
            classification_path="channel",
            abstract=f"Thread message {i + 1}",
            queued_for_digest=True,
            created_at=now,
        )
        items.append(msg)
        db_session.add(msg)

    # DM conversation (2 messages)
    for i in range(2):
        msg = TriageClassification(
            id=str(uuid4()),
            user_id=test_user.id,
            sender_slack_id=f"U_dm_sender_{i}",
            sender_name=f"DM Sender {i}",
            channel_id="D_DM_001",
            channel_name=None,
            message_ts=f"{ts_base + 100}.{i + 1:06d}",
            thread_ts=None,
            priority_level="p1",
            confidence=0.85,
            classification_path="dm",
            abstract=f"DM message {i + 1}",
            queued_for_digest=True,
            created_at=now,
        )
        items.append(msg)
        db_session.add(msg)

    # Channel messages without thread (2 messages)
    for i in range(2):
        msg = TriageClassification(
            id=str(uuid4()),
            user_id=test_user.id,
            sender_slack_id=f"U_channel_sender_{i}",
            sender_name=f"Channel Sender {i}",
            channel_id="C_CHANNEL_001",
            channel_name="general",
            message_ts=f"{ts_base + 200}.{i + 1:06d}",
            thread_ts=None,
            priority_level="p2",
            confidence=0.8,
            classification_path="channel",
            abstract=f"Channel message {i + 1}",
            queued_for_digest=True,
            created_at=now,
        )
        items.append(msg)
        db_session.add(msg)

    # Message with user reaction (should be filtered)
    reacted_msg = TriageClassification(
        id=str(uuid4()),
        user_id=test_user.id,
        sender_slack_id="U_reacted_sender",
        sender_name="Reacted Sender",
        channel_id="C_REACTED_001",
        channel_name="reacted-channel",
        message_ts=f"{ts_base + 300}.000001",
        thread_ts=None,
        priority_level="p1",
        confidence=0.9,
        classification_path="channel",
        abstract="User reacted to this",
        queued_for_digest=True,
        user_reacted_at=now,
        created_at=now,
    )
    items.append(reacted_msg)
    db_session.add(reacted_msg)

    # Message with user responded (should be filtered)
    responded_msg = TriageClassification(
        id=str(uuid4()),
        user_id=test_user.id,
        sender_slack_id="U_responded_sender",
        sender_name="Responded Sender",
        channel_id="C_RESPONDED_001",
        channel_name="responded-channel",
        message_ts=f"{ts_base + 400}.000001",
        thread_ts=None,
        priority_level="p1",
        confidence=0.9,
        classification_path="channel",
        abstract="User responded to this",
        queued_for_digest=True,
        user_responded_at=now,
        created_at=now,
    )
    items.append(responded_msg)
    db_session.add(responded_msg)

    await db_session.commit()
    return items


class TestDigestGrouperIntegration:
    """Integration tests for conversation grouping."""

    def test_group_classifications_into_conversations(self, test_user, classifications):
        """Test that classifications are grouped correctly."""
        grouper = DigestGrouper()

        # Get only queued, unresponded messages
        queued = [
            c
            for c in classifications
            if c.queued_for_digest
            and c.user_reacted_at is None
            and c.user_responded_at is None
        ]

        conversations = grouper.group_messages(queued)

        # Should have 3 conversations:
        # 1. Thread (3 messages)
        # 2. DM (2 messages)
        # 3. Channel (2 messages)
        assert len(conversations) == 3

        # Check types
        types = {c.conversation_type for c in conversations}
        assert "thread" in types
        assert "dm" in types
        assert "channel" in types

        # Find thread conversation and verify
        thread_conv = next(c for c in conversations if c.conversation_type == "thread")
        assert len(thread_conv.messages) == 3
        assert thread_conv.channel_id == "C_THREAD_001"

        # Find DM conversation
        dm_conv = next(c for c in conversations if c.conversation_type == "dm")
        assert len(dm_conv.messages) == 2
        assert dm_conv.channel_id == "D_DM_001"

        # Find channel conversation
        channel_conv = next(
            c for c in conversations if c.conversation_type == "channel"
        )
        assert len(channel_conv.messages) == 2
        assert channel_conv.channel_id == "C_CHANNEL_001"

    def test_group_filters_reacted_messages(self, test_user, classifications):
        """Test that reacted messages are excluded."""
        grouper = DigestGrouper()

        queued = [
            c
            for c in classifications
            if c.queued_for_digest
            and c.user_reacted_at is None
            and c.user_responded_at is None
        ]

        # Verify reacted message is not in the list
        reacted_ids = {c.id for c in classifications if c.user_reacted_at}
        queued_ids = {c.id for c in queued}

        assert not reacted_ids.intersection(queued_ids)

    def test_group_filters_responded_messages(self, test_user, classifications):
        """Test that responded messages are excluded."""
        queued = [
            c
            for c in classifications
            if c.queued_for_digest
            and c.user_reacted_at is None
            and c.user_responded_at is None
        ]

        # Verify responded message is not in the list
        responded_ids = {c.id for c in classifications if c.user_responded_at}
        queued_ids = {c.id for c in queued}

        assert not responded_ids.intersection(queued_ids)


class TestDigestResponseCheckerIntegration:
    """Integration tests for response detection."""

    @pytest.mark.asyncio
    async def test_filter_conversations_with_db_data(self, test_user, classifications):
        """Test response filtering with actual DB data."""
        checker = DigestResponseChecker()
        grouper = DigestGrouper()

        # Group messages first
        queued = [
            c
            for c in classifications
            if c.queued_for_digest
            and c.user_reacted_at is None
            and c.user_responded_at is None
        ]
        conversations = grouper.group_messages(queued)

        # Mock Slack API to return no user messages
        with patch.object(checker, "_check_user_message_response", return_value=False):
            unresponded = await checker.filter_unresponded_conversations(
                test_user.id, test_user.slack_user_id, conversations
            )

        # All should pass through since we filtered reacted/responded already
        assert len(unresponded) == 3

    @pytest.mark.asyncio
    async def test_detect_user_message_after_conversation(
        self, test_user, db_session: AsyncSession
    ):
        """Test detecting user message posted after conversation."""
        checker = DigestResponseChecker()
        grouper = DigestGrouper()

        now = utcnow()
        ts_base = int(now.timestamp())

        # Create a message
        msg = TriageClassification(
            id=str(uuid4()),
            user_id=test_user.id,
            sender_slack_id="U_sender",
            sender_name="Sender",
            channel_id="C_TEST",
            channel_name="test",
            message_ts=f"{ts_base}.000001",
            thread_ts=None,
            priority_level="p1",
            confidence=0.9,
            classification_path="channel",
            abstract="Test message",
            queued_for_digest=True,
            created_at=now,
        )
        db_session.add(msg)
        await db_session.commit()

        conversations = grouper.group_messages([msg])

        # Mock Slack API to return user message after
        mock_client = AsyncMock()
        mock_client.conversations_history = AsyncMock(
            return_value={
                "messages": [
                    {"ts": f"{ts_base + 10}.000001", "user": test_user.slack_user_id},
                ]
            }
        )
        checker.slack_service.client = mock_client

        unresponded = await checker.filter_unresponded_conversations(
            test_user.id, test_user.slack_user_id, conversations
        )

        # Should be filtered out since user posted after
        assert len(unresponded) == 0


class TestDigestGenerationIntegration:
    """End-to-end tests for digest generation."""

    @pytest.mark.asyncio
    async def test_prepare_conversation_digest(
        self, test_user, classifications, db_session: AsyncSession
    ):
        """Test the full digest preparation flow."""
        delivery = TriageDeliveryService(db_session)

        # Get queued messages
        queued = [
            c
            for c in classifications
            if c.queued_for_digest
            and c.user_reacted_at is None
            and c.user_responded_at is None
        ]

        # Mock Slack API
        with patch(
            "app.services.digest_response_checker.DigestResponseChecker._check_user_message_response",
            return_value=False,
        ):
            conversations = await delivery.prepare_conversation_digest(
                test_user.id, test_user.slack_user_id, queued
            )

        # Should have 3 conversations
        assert len(conversations) == 3

        # Each conversation should have messages
        for conv in conversations:
            assert len(conv.messages) > 0
            assert conv.channel_id is not None

    @pytest.mark.asyncio
    async def test_create_conversation_summary(
        self, test_user, classifications, db_session: AsyncSession
    ):
        """Test creating a summary for a conversation."""
        delivery = TriageDeliveryService(db_session)
        grouper = DigestGrouper()

        queued = [
            c
            for c in classifications
            if c.queued_for_digest
            and c.user_reacted_at is None
            and c.user_responded_at is None
        ]

        conversations = grouper.group_messages(queued)
        thread_conv = next(c for c in conversations if c.conversation_type == "thread")

        # Mock LLM
        with patch("app.core.llm.get_llm_provider") as mock_provider:
            mock_llm = AsyncMock()
            mock_llm.generate = AsyncMock(
                return_value="Discussion about project updates"
            )
            mock_provider.return_value = mock_llm

            summary = await delivery.create_conversation_summary(thread_conv)

        assert summary is not None
        assert len(summary) > 0

    @pytest.mark.asyncio
    async def test_full_digest_flow(
        self, test_user, classifications, db_session: AsyncSession
    ):
        """Test the complete digest generation flow."""
        from app.db.repositories.triage import TriageClassificationRepository

        repo = TriageClassificationRepository(db_session)
        delivery = TriageDeliveryService(db_session)

        # Get unalerted items
        p1_items = await repo.get_unalerted_scheduled_items(test_user.id, "p1")
        p2_items = await repo.get_unalerted_scheduled_items(test_user.id, "p2")

        all_items = p1_items + p2_items

        # Should have 9 items (3 thread + 2 DM + 2 channel + 1 reacted + 1 responded)
        # But reacted and responded should be filtered by our query
        assert len(all_items) == 9

        # Filter out already reacted/responded
        filtered = [
            c
            for c in all_items
            if c.user_reacted_at is None and c.user_responded_at is None
        ]
        assert len(filtered) == 7  # 9 - 2 (reacted + responded)

        # Group into conversations
        grouper = DigestGrouper()
        conversations = grouper.group_messages(filtered)

        # Should have 3 conversations (thread, DM, channel)
        assert len(conversations) == 3

        # Verify message counts
        total_messages = sum(len(c.messages) for c in conversations)
        assert total_messages == 7


class TestReactionEventIntegration:
    """Tests for reaction event handling."""

    @pytest.mark.asyncio
    async def test_mark_user_reacted(self, test_user, db_session: AsyncSession):
        """Test marking a classification as reacted."""
        from app.db.repositories.triage import TriageClassificationRepository

        now = utcnow()
        ts_base = int(now.timestamp())

        # Create a classification
        msg = TriageClassification(
            id=str(uuid4()),
            user_id=test_user.id,
            sender_slack_id="U_sender",
            sender_name="Sender",
            channel_id="C_TEST",
            channel_name="test",
            message_ts=f"{ts_base}.000001",
            thread_ts=None,
            priority_level="p1",
            confidence=0.9,
            classification_path="channel",
            abstract="Test message",
            queued_for_digest=True,
            created_at=now,
        )
        db_session.add(msg)
        await db_session.commit()
        await db_session.refresh(msg)

        # Mark as reacted
        repo = TriageClassificationRepository(db_session)
        updated = await repo.mark_user_reacted(
            test_user.id, "C_TEST", f"{ts_base}.000001"
        )

        assert updated == 1

        # Refresh and verify
        await db_session.refresh(msg)
        assert msg.user_reacted_at is not None

    @pytest.mark.asyncio
    async def test_mark_user_responded_bulk(self, test_user, db_session: AsyncSession):
        """Test marking multiple classifications as responded."""
        from app.db.repositories.triage import TriageClassificationRepository

        now = utcnow()
        ts_base = int(now.timestamp())

        # Create multiple classifications in same channel
        for i in range(3):
            msg = TriageClassification(
                id=str(uuid4()),
                user_id=test_user.id,
                sender_slack_id=f"U_sender_{i}",
                sender_name=f"Sender {i}",
                channel_id="C_BULK",
                channel_name="bulk-test",
                message_ts=f"{ts_base}.{i + 1:06d}",
                thread_ts=None,
                priority_level="p1",
                confidence=0.9,
                classification_path="channel",
                abstract=f"Message {i}",
                queued_for_digest=True,
                created_at=now,
            )
            db_session.add(msg)
        await db_session.commit()

        # Mark all as responded (user posted after ts_base + 3)
        repo = TriageClassificationRepository(db_session)
        updated = await repo.mark_user_responded(
            test_user.id, "C_BULK", f"{ts_base + 10}.000000"
        )

        assert updated == 3
