"""Tests for ConversationSummaryRepository."""

import pytest
from app.db.repositories.conversation_summary import ConversationSummaryRepository
from app.db.models.conversation_summary import ConversationSummary


@pytest.fixture
def repo(db_session):
    return ConversationSummaryRepository(db_session)


@pytest.mark.asyncio
async def test_create_conversation_summary(repo, test_user):
    summary = ConversationSummary(
        user_id=test_user.id,
        conversation_type="thread",
        channel_id="C123",
        channel_name="general",
        thread_ts="1234567890.123456",
        abstract="Test conversation",
        participants=[{"slack_id": "U123", "name": "Alice"}],
        message_count=3,
        priority_level="p2",
        first_message_ts="1234567890.123456",
    )

    created = await repo.create(summary)

    assert created.id is not None
    assert created.conversation_type == "thread"
    assert created.message_count == 3
    assert created.priority_level == "p2"


@pytest.mark.asyncio
async def test_get_by_digest_no_results(repo, test_user):
    conversations = await repo.get_by_digest("00000000-0000-0000-0000-000000000000")
    assert len(conversations) == 0
    
    count = await repo.count_by_digest("00000000-0000-0000-0000-000000000000")
    assert count == 0


@pytest.mark.asyncio
async def test_get_recent_thread_summary(repo, test_user):
    summary = ConversationSummary(
        user_id=test_user.id,
        conversation_type="thread",
        channel_id="C123",
        channel_name="general",
        thread_ts="1234567890.123456",
        abstract="Earlier conversation about pricing",
        message_count=5,
        priority_level="p2",
        first_message_ts="1234567890.123456",
    )
    await repo.create(summary)

    recent = await repo.get_recent_thread_summary(
        thread_ts="1234567890.123456",
        user_id=test_user.id,
        channel_id="C123",
        days=7,
    )

    assert recent is not None
    assert recent.abstract == "Earlier conversation about pricing"

    recent_other_thread = await repo.get_recent_thread_summary(
        thread_ts="9999999999.999999",
        user_id=test_user.id,
        channel_id="C123",
        days=7,
    )
    assert recent_other_thread is None


@pytest.mark.asyncio
async def test_mark_reviewed(repo, test_user):
    summary = ConversationSummary(
        user_id=test_user.id,
        conversation_type="thread",
        channel_id="C123",
        channel_name="general",
        thread_ts="1234567890.123456",
        abstract="Test conversation",
        message_count=2,
        priority_level="p2",
        first_message_ts="1234567890.123456",
    )
    created = await repo.create(summary)
    assert created.reviewed_at is None
    
    await repo.mark_reviewed(created.id)
    
    updated = await repo.get(created.id)
    assert updated is not None
    assert updated.reviewed_at is not None
