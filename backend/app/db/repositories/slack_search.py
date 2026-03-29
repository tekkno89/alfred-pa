"""Repositories for Slack search channel participation and summaries."""

from datetime import datetime

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.slack_search import SlackChannelSummary, UserChannelParticipation
from app.db.repositories.base import BaseRepository


class UserChannelParticipationRepository(BaseRepository[UserChannelParticipation]):
    """Repository for user channel participation data."""

    def __init__(self, db: AsyncSession):
        super().__init__(UserChannelParticipation, db)

    async def get_by_user(
        self, user_id: str, limit: int = 50, include_archived: bool = False
    ) -> list[UserChannelParticipation]:
        """Get ranked channel list for a user."""
        query = (
            select(UserChannelParticipation)
            .where(UserChannelParticipation.user_id == user_id)
        )
        if not include_archived:
            query = query.where(UserChannelParticipation.is_archived == False)  # noqa: E712
        query = query.order_by(UserChannelParticipation.participation_rank).limit(limit)
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def get_channel_ids_for_user(
        self, user_id: str, limit: int = 50, include_archived: bool = False
    ) -> list[str]:
        """Get just channel IDs for a user, ranked."""
        query = (
            select(UserChannelParticipation.channel_id)
            .where(UserChannelParticipation.user_id == user_id)
        )
        if not include_archived:
            query = query.where(UserChannelParticipation.is_archived == False)  # noqa: E712
        query = query.order_by(UserChannelParticipation.participation_rank).limit(limit)
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def get_by_channel_name(
        self, user_id: str, channel_name: str
    ) -> UserChannelParticipation | None:
        """Look up a channel by name for a user."""
        query = (
            select(UserChannelParticipation)
            .where(
                UserChannelParticipation.user_id == user_id,
                UserChannelParticipation.channel_name == channel_name,
            )
        )
        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    async def upsert_batch(
        self, user_id: str, channels: list[dict]
    ) -> int:
        """Delete-and-replace all participation data for a user."""
        await self.db.execute(
            delete(UserChannelParticipation).where(
                UserChannelParticipation.user_id == user_id
            )
        )
        for i, ch in enumerate(channels):
            obj = UserChannelParticipation(
                user_id=user_id,
                channel_id=ch["channel_id"],
                channel_name=ch["channel_name"],
                channel_type=ch["channel_type"],
                participation_rank=i,
                is_member=ch.get("is_member", True),
                is_archived=ch.get("is_archived", False),
                member_count=ch.get("member_count", 0),
                last_activity_at=ch.get("last_activity_at"),
            )
            self.db.add(obj)
        await self.db.flush()
        return len(channels)


class SlackChannelSummaryRepository(BaseRepository[SlackChannelSummary]):
    """Repository for Slack channel summaries."""

    def __init__(self, db: AsyncSession):
        super().__init__(SlackChannelSummary, db)

    async def get_by_channel_id(self, channel_id: str) -> SlackChannelSummary | None:
        """Get a single summary by channel ID."""
        query = select(SlackChannelSummary).where(
            SlackChannelSummary.channel_id == channel_id
        )
        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    async def get_by_channel_ids(
        self, channel_ids: list[str]
    ) -> list[SlackChannelSummary]:
        """Batch fetch summaries by channel IDs."""
        if not channel_ids:
            return []
        query = select(SlackChannelSummary).where(
            SlackChannelSummary.channel_id.in_(channel_ids)
        )
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def get_all_public(self) -> list[SlackChannelSummary]:
        """Get all public channel summaries."""
        query = select(SlackChannelSummary).where(
            SlackChannelSummary.channel_type == "public"
        )
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def upsert(
        self,
        channel_id: str,
        channel_name: str,
        channel_type: str,
        summary: str,
        member_count: int,
        is_archived: bool,
        generated_by_user_id: str,
    ) -> SlackChannelSummary:
        """Create or update a channel summary."""
        existing = await self.get_by_channel_id(channel_id)
        now = datetime.utcnow()
        if existing:
            existing.channel_name = channel_name
            existing.channel_type = channel_type
            existing.summary = summary
            existing.member_count = member_count
            existing.is_archived = is_archived
            existing.generated_by_user_id = generated_by_user_id
            existing.last_summarized_at = now
            await self.db.flush()
            await self.db.refresh(existing)
            return existing
        else:
            obj = SlackChannelSummary(
                channel_id=channel_id,
                channel_name=channel_name,
                channel_type=channel_type,
                summary=summary,
                member_count=member_count,
                is_archived=is_archived,
                generated_by_user_id=generated_by_user_id,
                last_summarized_at=now,
            )
            self.db.add(obj)
            await self.db.flush()
            await self.db.refresh(obj)
            return obj
