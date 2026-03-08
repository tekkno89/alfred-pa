from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import Session
from app.db.repositories.base import BaseRepository

# Tools that mark a session as "utility" (hidden from UI by default)
UTILITY_TOOLS = {"manage_todos", "focus_mode", "manage_calendar"}


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
        starred: bool | None = None,
        include_utility: bool = False,
    ) -> list[Session]:
        """Get sessions for a specific user, ordered by most recent.

        By default, utility sessions (task/focus interactions) are hidden.
        Pass include_utility=True to include them.
        """
        query = (
            select(Session)
            .where(Session.user_id == user_id)
            .order_by(Session.updated_at.desc())
            .offset(skip)
            .limit(limit)
        )
        if starred is not None:
            query = query.where(Session.is_starred == starred)
        if not include_utility:
            query = query.where(
                or_(Session.session_type != "utility", Session.session_type.is_(None))
            )
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def count_user_sessions(
        self,
        user_id: str,
        *,
        starred: bool | None = None,
        include_utility: bool = False,
    ) -> int:
        """Count sessions for a specific user."""
        query = (
            select(func.count())
            .select_from(Session)
            .where(Session.user_id == user_id)
        )
        if starred is not None:
            query = query.where(Session.is_starred == starred)
        if not include_utility:
            query = query.where(
                or_(Session.session_type != "utility", Session.session_type.is_(None))
            )
        result = await self.db.execute(query)
        return result.scalar() or 0

    async def create_session(
        self,
        user_id: str,
        title: str | None = None,
        source: str = "webapp",
        slack_channel_id: str | None = None,
        slack_thread_ts: str | None = None,
        session_type: str | None = None,
    ) -> Session:
        """Create a new session."""
        session = Session(
            user_id=user_id,
            title=title,
            source=source,
            slack_channel_id=slack_channel_id,
            slack_thread_ts=slack_thread_ts,
            session_type=session_type,
        )
        return await self.create(session)

    async def classify_session(
        self, session: Session, tools_used: set[str]
    ) -> None:
        """Classify a session based on which tools were used.

        Only classifies on the first exchange (when session_type is None).
        Once classified, the type is locked.

        Rules:
        - If already classified, no change.
        - If only utility tools used (>=1, all in UTILITY_TOOLS) -> 'utility'
        - Otherwise -> 'conversation'
        """
        if session.session_type is not None:
            return
        if session.source == "slack" and tools_used and tools_used <= UTILITY_TOOLS:
            await self.update(session, session_type="utility")
        else:
            await self.update(session, session_type="conversation")

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
