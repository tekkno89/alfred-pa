from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import Session
from app.db.repositories.base import BaseRepository


class SessionRepository(BaseRepository[Session]):
    """Repository for Session model."""

    def __init__(self, db: AsyncSession):
        super().__init__(Session, db)

    async def get_with_messages(self, session_id: str) -> Session | None:
        """Get a session with its messages loaded."""
        result = await self.db.execute(
            select(Session)
            .options(selectinload(Session.messages))
            .where(Session.id == session_id)
        )
        return result.scalar_one_or_none()

    async def get_user_sessions(
        self,
        user_id: str,
        *,
        skip: int = 0,
        limit: int = 20,
    ) -> list[Session]:
        """Get sessions for a specific user, ordered by most recent."""
        return await self.get_multi(
            user_id=user_id,
            skip=skip,
            limit=limit,
            order_by=Session.updated_at.desc(),
        )

    async def count_user_sessions(self, user_id: str) -> int:
        """Count sessions for a specific user."""
        return await self.count(user_id=user_id)

    async def create_session(
        self,
        user_id: str,
        title: str | None = None,
        source: str = "webapp",
        slack_channel_id: str | None = None,
        slack_thread_ts: str | None = None,
    ) -> Session:
        """Create a new session."""
        session = Session(
            user_id=user_id,
            title=title,
            source=source,
            slack_channel_id=slack_channel_id,
            slack_thread_ts=slack_thread_ts,
        )
        return await self.create(session)

    async def get_by_slack_thread(
        self,
        channel_id: str,
        thread_ts: str,
    ) -> Session | None:
        """
        Get a session by Slack channel and thread timestamp.

        Args:
            channel_id: Slack channel ID
            thread_ts: Slack thread timestamp

        Returns:
            Session if found, None otherwise
        """
        result = await self.db.execute(
            select(Session).where(
                Session.slack_channel_id == channel_id,
                Session.slack_thread_ts == thread_ts,
            )
        )
        return result.scalar_one_or_none()
