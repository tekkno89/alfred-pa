"""Repository for ConversationSummary operations."""

from datetime import datetime, timedelta

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.conversation_summary import ConversationSummary
from app.db.repositories.base import BaseRepository


class ConversationSummaryRepository(BaseRepository[ConversationSummary]):
    """Repository for ConversationSummary CRUD operations."""

    def __init__(self, db: AsyncSession):
        super().__init__(ConversationSummary, db)

    async def get_by_digest(
        self,
        digest_id: str,
        priority: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> list[ConversationSummary]:
        """Get conversations for a digest, optionally filtered by priority."""
        query = (
            select(ConversationSummary)
            .where(ConversationSummary.digest_summary_id == digest_id)
            .order_by(ConversationSummary.first_message_at.desc())
        )
        if priority:
            query = query.where(ConversationSummary.priority_level == priority)
        query = query.offset(offset).limit(limit)
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def count_by_digest(
        self, digest_id: str, priority: str | None = None
    ) -> int:
        """Count conversations for a digest."""
        query = select(func.count()).select_from(ConversationSummary).where(
            ConversationSummary.digest_summary_id == digest_id
        )
        if priority:
            query = query.where(ConversationSummary.priority_level == priority)
        result = await self.db.execute(query)
        return result.scalar() or 0

    async def get_with_messages(
        self, summary_id: str
    ) -> ConversationSummary | None:
        """Get a conversation summary (messages loaded via relationship)."""
        result = await self.db.execute(
            select(ConversationSummary).where(ConversationSummary.id == summary_id)
        )
        return result.scalar_one_or_none()

    async def get_recent_thread_summary(
        self,
        thread_ts: str,
        user_id: str,
        channel_id: str,
        days: int = 7,
    ) -> ConversationSummary | None:
        """Get the most recent conversation summary for a thread.
        
        Used for contextual abstract generation when new messages arrive
        in a previously summarized thread.
        """
        cutoff = datetime.utcnow() - timedelta(days=days)
        result = await self.db.execute(
            select(ConversationSummary)
            .where(ConversationSummary.thread_ts == thread_ts)
            .where(ConversationSummary.user_id == user_id)
            .where(ConversationSummary.channel_id == channel_id)
            .where(ConversationSummary.created_at >= cutoff)
            .order_by(ConversationSummary.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def link_to_digest(
        self, conversation_ids: list[str], digest_id: str
    ) -> None:
        """Link conversations to a digest summary."""
        if not conversation_ids:
            return
        await self.db.execute(
            update(ConversationSummary)
            .where(ConversationSummary.id.in_(conversation_ids))
            .values(digest_summary_id=digest_id)
        )
        await self.db.flush()

    async def mark_reviewed(self, conversation_id: str) -> None:
        """Mark a conversation as reviewed."""
        await self.db.execute(
            update(ConversationSummary)
            .where(ConversationSummary.id == conversation_id)
            .values(reviewed_at=func.now())
        )
        await self.db.flush()
