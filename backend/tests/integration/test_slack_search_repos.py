"""Integration tests for Slack search repositories."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.slack_search import SlackChannelSummary, UserChannelParticipation
from app.db.repositories.slack_search import (
    SlackChannelSummaryRepository,
    UserChannelParticipationRepository,
)
from tests.factories import UserFactory


@pytest.fixture
async def test_user(db_session: AsyncSession):
    """Create a test user."""
    user = UserFactory()
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


class TestUserChannelParticipationRepository:
    """Tests for UserChannelParticipationRepository."""

    async def test_upsert_batch_inserts(self, db_session: AsyncSession, test_user):
        """Should insert participation records."""
        repo = UserChannelParticipationRepository(db_session)

        channels = [
            {
                "channel_id": "C001",
                "channel_name": "general",
                "channel_type": "public",
                "is_member": True,
                "is_archived": False,
                "member_count": 50,
            },
            {
                "channel_id": "C002",
                "channel_name": "engineering",
                "channel_type": "private",
                "is_member": True,
                "is_archived": False,
                "member_count": 10,
            },
        ]

        count = await repo.upsert_batch(test_user.id, channels)
        await db_session.commit()

        assert count == 2

        result = await repo.get_by_user(test_user.id)
        assert len(result) == 2
        assert result[0].channel_name == "general"
        assert result[0].participation_rank == 0
        assert result[1].channel_name == "engineering"
        assert result[1].participation_rank == 1

    async def test_upsert_batch_replaces(self, db_session: AsyncSession, test_user):
        """Should delete-and-replace all participation data for a user."""
        repo = UserChannelParticipationRepository(db_session)

        # First batch
        await repo.upsert_batch(
            test_user.id,
            [
                {
                    "channel_id": "C001",
                    "channel_name": "general",
                    "channel_type": "public",
                    "is_member": True,
                    "is_archived": False,
                    "member_count": 50,
                },
            ],
        )
        await db_session.commit()

        # Second batch (replaces first)
        count = await repo.upsert_batch(
            test_user.id,
            [
                {
                    "channel_id": "C003",
                    "channel_name": "random",
                    "channel_type": "public",
                    "is_member": True,
                    "is_archived": False,
                    "member_count": 30,
                },
            ],
        )
        await db_session.commit()

        assert count == 1

        result = await repo.get_by_user(test_user.id)
        assert len(result) == 1
        assert result[0].channel_name == "random"

    async def test_get_by_user_respects_archive_filter(
        self, db_session: AsyncSession, test_user
    ):
        """Should filter out archived channels by default."""
        repo = UserChannelParticipationRepository(db_session)

        await repo.upsert_batch(
            test_user.id,
            [
                {
                    "channel_id": "C001",
                    "channel_name": "active",
                    "channel_type": "public",
                    "is_member": True,
                    "is_archived": False,
                    "member_count": 10,
                },
                {
                    "channel_id": "C002",
                    "channel_name": "archived",
                    "channel_type": "public",
                    "is_member": True,
                    "is_archived": True,
                    "member_count": 5,
                },
            ],
        )
        await db_session.commit()

        # Default: exclude archived
        result = await repo.get_by_user(test_user.id)
        assert len(result) == 1
        assert result[0].channel_name == "active"

        # Include archived
        result = await repo.get_by_user(test_user.id, include_archived=True)
        assert len(result) == 2

    async def test_get_channel_ids_for_user(
        self, db_session: AsyncSession, test_user
    ):
        """Should return just channel IDs."""
        repo = UserChannelParticipationRepository(db_session)

        await repo.upsert_batch(
            test_user.id,
            [
                {
                    "channel_id": "C001",
                    "channel_name": "general",
                    "channel_type": "public",
                    "is_member": True,
                    "is_archived": False,
                    "member_count": 50,
                },
            ],
        )
        await db_session.commit()

        ids = await repo.get_channel_ids_for_user(test_user.id)
        assert ids == ["C001"]

    async def test_get_by_channel_name(
        self, db_session: AsyncSession, test_user
    ):
        """Should look up channel by name."""
        repo = UserChannelParticipationRepository(db_session)

        await repo.upsert_batch(
            test_user.id,
            [
                {
                    "channel_id": "C001",
                    "channel_name": "general",
                    "channel_type": "public",
                    "is_member": True,
                    "is_archived": False,
                    "member_count": 50,
                },
            ],
        )
        await db_session.commit()

        result = await repo.get_by_channel_name(test_user.id, "general")
        assert result is not None
        assert result.channel_id == "C001"

        result = await repo.get_by_channel_name(test_user.id, "nonexistent")
        assert result is None


class TestSlackChannelSummaryRepository:
    """Tests for SlackChannelSummaryRepository."""

    async def test_upsert_creates(self, db_session: AsyncSession, test_user):
        """Should create a new summary."""
        repo = SlackChannelSummaryRepository(db_session)

        summary = await repo.upsert(
            channel_id="C001",
            channel_name="general",
            channel_type="public",
            summary="General discussion channel",
            member_count=50,
            is_archived=False,
            generated_by_user_id=test_user.id,
        )
        await db_session.commit()

        assert summary.channel_id == "C001"
        assert summary.summary == "General discussion channel"

    async def test_upsert_updates(self, db_session: AsyncSession, test_user):
        """Should update an existing summary."""
        repo = SlackChannelSummaryRepository(db_session)

        await repo.upsert(
            channel_id="C010",
            channel_name="engineering",
            channel_type="public",
            summary="Old summary",
            member_count=10,
            is_archived=False,
            generated_by_user_id=test_user.id,
        )
        await db_session.commit()

        updated = await repo.upsert(
            channel_id="C010",
            channel_name="engineering",
            channel_type="public",
            summary="Updated summary",
            member_count=12,
            is_archived=False,
            generated_by_user_id=test_user.id,
        )
        await db_session.commit()

        assert updated.summary == "Updated summary"
        assert updated.member_count == 12

    async def test_get_by_channel_id(self, db_session: AsyncSession, test_user):
        """Should fetch summary by channel ID."""
        repo = SlackChannelSummaryRepository(db_session)

        await repo.upsert(
            channel_id="C020",
            channel_name="random",
            channel_type="public",
            summary="Random stuff",
            member_count=30,
            is_archived=False,
            generated_by_user_id=test_user.id,
        )
        await db_session.commit()

        result = await repo.get_by_channel_id("C020")
        assert result is not None
        assert result.summary == "Random stuff"

        result = await repo.get_by_channel_id("NONEXISTENT")
        assert result is None

    async def test_get_by_channel_ids_batch(
        self, db_session: AsyncSession, test_user
    ):
        """Should batch fetch summaries."""
        repo = SlackChannelSummaryRepository(db_session)

        await repo.upsert(
            channel_id="C030",
            channel_name="ch-a",
            channel_type="public",
            summary="Summary A",
            member_count=5,
            is_archived=False,
            generated_by_user_id=test_user.id,
        )
        await repo.upsert(
            channel_id="C031",
            channel_name="ch-b",
            channel_type="private",
            summary="Summary B",
            member_count=3,
            is_archived=False,
            generated_by_user_id=test_user.id,
        )
        await db_session.commit()

        results = await repo.get_by_channel_ids(["C030", "C031", "MISSING"])
        assert len(results) == 2
        channel_ids = {r.channel_id for r in results}
        assert "C030" in channel_ids
        assert "C031" in channel_ids

    async def test_get_all_public(self, db_session: AsyncSession, test_user):
        """Should return only public channel summaries."""
        repo = SlackChannelSummaryRepository(db_session)

        await repo.upsert(
            channel_id="C040",
            channel_name="public-ch",
            channel_type="public",
            summary="Public",
            member_count=10,
            is_archived=False,
            generated_by_user_id=test_user.id,
        )
        await repo.upsert(
            channel_id="C041",
            channel_name="private-ch",
            channel_type="private",
            summary="Private",
            member_count=3,
            is_archived=False,
            generated_by_user_id=test_user.id,
        )
        await db_session.commit()

        results = await repo.get_all_public()
        channel_types = {r.channel_type for r in results}
        assert "private" not in channel_types
