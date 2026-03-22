"""Repositories for triage system operations."""

from datetime import datetime, timedelta

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.focus import FocusModeState
from app.db.models.triage import (
    ChannelKeywordRule,
    ChannelSourceExclusion,
    MonitoredChannel,
    SenderBehaviorModel,
    TriageClassification,
    TriageFeedback,
    TriageUserSettings,
)
from app.db.repositories.base import BaseRepository


class TriageUserSettingsRepository(BaseRepository[TriageUserSettings]):
    """Repository for TriageUserSettings CRUD operations."""

    def __init__(self, db: AsyncSession):
        super().__init__(TriageUserSettings, db)

    async def get_by_user_id(self, user_id: str) -> TriageUserSettings | None:
        result = await self.db.execute(
            select(TriageUserSettings).where(
                TriageUserSettings.user_id == user_id
            )
        )
        return result.scalar_one_or_none()

    async def get_or_create(self, user_id: str) -> TriageUserSettings:
        settings = await self.get_by_user_id(user_id)
        if not settings:
            settings = TriageUserSettings(user_id=user_id)
            settings = await self.create(settings)
        return settings


class MonitoredChannelRepository(BaseRepository[MonitoredChannel]):
    """Repository for MonitoredChannel CRUD operations."""

    def __init__(self, db: AsyncSession):
        super().__init__(MonitoredChannel, db)

    async def get_by_user(
        self, user_id: str, active_only: bool = True
    ) -> list[MonitoredChannel]:
        query = select(MonitoredChannel).where(
            MonitoredChannel.user_id == user_id
        )
        if active_only:
            query = query.where(MonitoredChannel.is_active == True)  # noqa: E712
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def get_users_for_channel(
        self, slack_channel_id: str
    ) -> list[MonitoredChannel]:
        """Get all users monitoring a specific Slack channel (active only)."""
        result = await self.db.execute(
            select(MonitoredChannel)
            .where(MonitoredChannel.slack_channel_id == slack_channel_id)
            .where(MonitoredChannel.is_active == True)  # noqa: E712
        )
        return list(result.scalars().all())

    async def get_all_active_channel_ids(self) -> list[str]:
        """Get all unique active monitored channel IDs across all users."""
        result = await self.db.execute(
            select(MonitoredChannel.slack_channel_id)
            .where(MonitoredChannel.is_active == True)  # noqa: E712
            .distinct()
        )
        return list(result.scalars().all())

    async def get_by_user_and_channel(
        self, user_id: str, slack_channel_id: str
    ) -> MonitoredChannel | None:
        result = await self.db.execute(
            select(MonitoredChannel)
            .where(MonitoredChannel.user_id == user_id)
            .where(MonitoredChannel.slack_channel_id == slack_channel_id)
        )
        return result.scalar_one_or_none()


class ChannelKeywordRuleRepository(BaseRepository[ChannelKeywordRule]):
    """Repository for ChannelKeywordRule CRUD operations."""

    def __init__(self, db: AsyncSession):
        super().__init__(ChannelKeywordRule, db)

    async def get_by_channel(
        self, monitored_channel_id: str, user_id: str
    ) -> list[ChannelKeywordRule]:
        result = await self.db.execute(
            select(ChannelKeywordRule)
            .where(ChannelKeywordRule.monitored_channel_id == monitored_channel_id)
            .where(ChannelKeywordRule.user_id == user_id)
        )
        return list(result.scalars().all())


class ChannelSourceExclusionRepository(BaseRepository[ChannelSourceExclusion]):
    """Repository for ChannelSourceExclusion CRUD operations."""

    def __init__(self, db: AsyncSession):
        super().__init__(ChannelSourceExclusion, db)

    async def get_by_channel(
        self, monitored_channel_id: str, user_id: str
    ) -> list[ChannelSourceExclusion]:
        result = await self.db.execute(
            select(ChannelSourceExclusion)
            .where(
                ChannelSourceExclusion.monitored_channel_id == monitored_channel_id
            )
            .where(ChannelSourceExclusion.user_id == user_id)
        )
        return list(result.scalars().all())

    async def get_includes_for_channel(
        self, slack_channel_id: str
    ) -> list[ChannelSourceExclusion]:
        """Get all 'include' overrides for a channel across users."""
        result = await self.db.execute(
            select(ChannelSourceExclusion)
            .join(MonitoredChannel)
            .where(MonitoredChannel.slack_channel_id == slack_channel_id)
            .where(ChannelSourceExclusion.action == "include")
        )
        return list(result.scalars().all())


class TriageClassificationRepository(BaseRepository[TriageClassification]):
    """Repository for TriageClassification CRUD operations."""

    def __init__(self, db: AsyncSession):
        super().__init__(TriageClassification, db)

    async def get_by_session(
        self,
        user_id: str,
        focus_session_id: str,
        focus_started_at: "datetime | None" = None,
    ) -> list[TriageClassification]:
        query = (
            select(TriageClassification)
            .where(TriageClassification.user_id == user_id)
            .where(TriageClassification.focus_session_id == focus_session_id)
        )
        if focus_started_at:
            query = query.where(
                TriageClassification.focus_started_at == focus_started_at
            )
        query = query.order_by(TriageClassification.created_at.desc())
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def get_unsurfaced_digest_items(
        self,
        user_id: str,
        focus_session_id: str,
        focus_started_at: "datetime | None" = None,
    ) -> list[TriageClassification]:
        """Get digest items not yet surfaced/consolidated."""
        query = (
            select(TriageClassification)
            .where(TriageClassification.user_id == user_id)
            .where(TriageClassification.focus_session_id == focus_session_id)
            .where(TriageClassification.urgency_level == "digest")
            .where(TriageClassification.surfaced_at_break == False)  # noqa: E712
            .where(TriageClassification.digest_summary_id.is_(None))
        )
        if focus_started_at:
            query = query.where(
                TriageClassification.focus_started_at == focus_started_at
            )
        query = query.order_by(TriageClassification.created_at.asc())
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def mark_surfaced_at_break(self, ids: list[str]) -> None:
        if not ids:
            return
        await self.db.execute(
            update(TriageClassification)
            .where(TriageClassification.id.in_(ids))
            .values(surfaced_at_break=True)
        )
        await self.db.flush()

    def _apply_filters(
        self,
        query,
        user_id: str,
        urgency_level: str | None = None,
        channel_id: str | None = None,
        reviewed: bool | None = None,
        exclude_active_session_digest: bool = False,
    ):
        """Apply common filter logic to a query."""
        query = query.where(TriageClassification.user_id == user_id)
        # Hide items that have been consolidated into a digest summary
        query = query.where(
            TriageClassification.digest_summary_id.is_(None)
        )
        if urgency_level:
            query = query.where(
                TriageClassification.urgency_level == urgency_level
            )
        if channel_id:
            query = query.where(TriageClassification.channel_id == channel_id)
        if reviewed is True:
            query = query.where(
                TriageClassification.reviewed_at.isnot(None)
            )
        elif reviewed is False:
            query = query.where(
                TriageClassification.reviewed_at.is_(None)
            )
        if exclude_active_session_digest:
            active_session_ids = select(FocusModeState.id).where(
                FocusModeState.is_active == True  # noqa: E712
            )
            query = query.where(
                ~(
                    (TriageClassification.urgency_level.in_(["digest", "noise"]))
                    & (TriageClassification.focus_session_id.in_(active_session_ids))
                )
            )
        return query

    async def get_recent(
        self,
        user_id: str,
        limit: int = 50,
        offset: int = 0,
        urgency_level: str | None = None,
        channel_id: str | None = None,
        reviewed: bool | None = None,
        exclude_active_session_digest: bool = False,
    ) -> list[TriageClassification]:
        query = select(TriageClassification).order_by(
            TriageClassification.created_at.desc()
        )
        query = self._apply_filters(
            query, user_id, urgency_level, channel_id,
            reviewed, exclude_active_session_digest,
        )
        query = query.offset(offset).limit(limit)
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def count_filtered(
        self,
        user_id: str,
        urgency_level: str | None = None,
        channel_id: str | None = None,
        reviewed: bool | None = None,
        exclude_active_session_digest: bool = False,
    ) -> int:
        """Count classifications matching the same filters as get_recent."""
        query = select(func.count()).select_from(TriageClassification)
        query = self._apply_filters(
            query, user_id, urgency_level, channel_id,
            reviewed, exclude_active_session_digest,
        )
        result = await self.db.execute(query)
        return result.scalar() or 0

    async def mark_reviewed(
        self, ids: list[str], user_id: str
    ) -> int:
        """Mark classifications as reviewed. Returns count updated."""
        if not ids:
            return 0
        result = await self.db.execute(
            update(TriageClassification)
            .where(TriageClassification.id.in_(ids))
            .where(TriageClassification.user_id == user_id)
            .values(reviewed_at=func.now())
        )
        await self.db.flush()
        return result.rowcount

    async def mark_unreviewed(
        self, ids: list[str], user_id: str
    ) -> int:
        """Mark classifications as unreviewed. Returns count updated."""
        if not ids:
            return 0
        result = await self.db.execute(
            update(TriageClassification)
            .where(TriageClassification.id.in_(ids))
            .where(TriageClassification.user_id == user_id)
            .values(reviewed_at=None)
        )
        await self.db.flush()
        return result.rowcount

    async def get_digest_children(
        self, summary_id: str, user_id: str
    ) -> list[TriageClassification]:
        """Get individual items consolidated into a digest summary."""
        result = await self.db.execute(
            select(TriageClassification)
            .where(TriageClassification.digest_summary_id == summary_id)
            .where(TriageClassification.user_id == user_id)
            .order_by(TriageClassification.created_at.asc())
        )
        return list(result.scalars().all())

    async def link_to_summary(self, ids: list[str], summary_id: str) -> None:
        """Link digest items to their summary row."""
        if not ids:
            return
        await self.db.execute(
            update(TriageClassification)
            .where(TriageClassification.id.in_(ids))
            .values(digest_summary_id=summary_id)
        )
        await self.db.flush()

    async def delete_expired(self, user_id: str, retention_days: int) -> int:
        """Delete classifications older than retention_days. Returns count deleted."""
        cutoff = datetime.utcnow() - timedelta(days=retention_days)
        result = await self.db.execute(
            delete(TriageClassification)
            .where(TriageClassification.user_id == user_id)
            .where(TriageClassification.created_at < cutoff)
        )
        await self.db.flush()
        return result.rowcount


class SenderBehaviorModelRepository(BaseRepository[SenderBehaviorModel]):
    """Repository for SenderBehaviorModel CRUD operations."""

    def __init__(self, db: AsyncSession):
        super().__init__(SenderBehaviorModel, db)

    async def get_for_sender(
        self, user_id: str, sender_slack_id: str
    ) -> SenderBehaviorModel | None:
        result = await self.db.execute(
            select(SenderBehaviorModel)
            .where(SenderBehaviorModel.user_id == user_id)
            .where(SenderBehaviorModel.sender_slack_id == sender_slack_id)
        )
        return result.scalar_one_or_none()

    async def upsert(
        self,
        user_id: str,
        sender_slack_id: str,
        **fields: object,
    ) -> SenderBehaviorModel:
        existing = await self.get_for_sender(user_id, sender_slack_id)
        if existing:
            return await self.update(existing, **fields)
        model = SenderBehaviorModel(
            user_id=user_id,
            sender_slack_id=sender_slack_id,
            **fields,
        )
        return await self.create(model)


class TriageFeedbackRepository(BaseRepository[TriageFeedback]):
    """Repository for TriageFeedback CRUD operations."""

    def __init__(self, db: AsyncSession):
        super().__init__(TriageFeedback, db)

    async def create_feedback(
        self,
        classification_id: str,
        user_id: str,
        was_correct: bool,
        correct_urgency: str | None = None,
    ) -> TriageFeedback:
        feedback = TriageFeedback(
            classification_id=classification_id,
            user_id=user_id,
            was_correct=was_correct,
            correct_urgency=correct_urgency,
        )
        return await self.create(feedback)
