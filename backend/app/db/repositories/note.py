"""Note repository."""

from sqlalchemy import case, select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.note import Note
from app.db.repositories.base import BaseRepository


class NoteRepository(BaseRepository[Note]):
    """Repository for Note model."""

    def __init__(self, db: AsyncSession):
        super().__init__(Note, db)

    async def create_note(
        self,
        user_id: str,
        title: str = "",
        body: str = "",
        is_favorited: bool = False,
        tags: list[str] | None = None,
    ) -> Note:
        """Create a new note."""
        note = Note(
            user_id=user_id,
            title=title,
            body=body,
            is_favorited=is_favorited,
            tags=tags or [],
        )
        return await self.create(note)

    async def get_user_notes(
        self,
        user_id: str,
        *,
        archived: bool = False,
        favorited: bool | None = None,
        skip: int = 0,
        limit: int = 20,
        sort_by: str = "updated_at",
    ) -> list[Note]:
        """Get notes for a user. Favorites pinned to top, then sorted."""
        query = (
            select(Note)
            .where(Note.user_id == user_id)
            .where(Note.is_archived == archived)
        )

        if favorited is not None:
            query = query.where(Note.is_favorited == favorited)

        # Pin favorites to top, then sort by chosen field
        order_col = getattr(Note, sort_by, Note.updated_at)
        query = query.order_by(
            case((Note.is_favorited == True, 0), else_=1),  # noqa: E712
            order_col.desc(),
        )

        query = query.offset(skip).limit(limit)
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def count_user_notes(
        self,
        user_id: str,
        *,
        archived: bool = False,
        favorited: bool | None = None,
    ) -> int:
        """Count notes for a user."""
        query = (
            select(func.count())
            .select_from(Note)
            .where(Note.user_id == user_id)
            .where(Note.is_archived == archived)
        )

        if favorited is not None:
            query = query.where(Note.is_favorited == favorited)

        result = await self.db.execute(query)
        return result.scalar() or 0

    async def get_recent_notes(
        self,
        user_id: str,
        limit: int = 5,
    ) -> list[Note]:
        """Get recent non-archived notes, for the dashboard card."""
        query = (
            select(Note)
            .where(Note.user_id == user_id)
            .where(Note.is_archived == False)  # noqa: E712
            .order_by(Note.updated_at.desc())
            .limit(limit)
        )
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def update_note(self, note: Note, **updates: str | bool) -> Note:
        """Update a note's fields."""
        return await self.update(note, **updates)
