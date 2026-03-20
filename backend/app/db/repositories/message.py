from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Message
from app.db.repositories.base import BaseRepository


class MessageRepository(BaseRepository[Message]):
    """Repository for Message model."""

    def __init__(self, db: AsyncSession):
        super().__init__(Message, db)

    async def get_session_messages(
        self,
        session_id: str,
        *,
        skip: int = 0,
        limit: int = 100,
    ) -> list[Message]:
        """Get messages for a specific session, ordered by creation time."""
        return await self.get_multi(
            session_id=session_id,
            skip=skip,
            limit=limit,
            order_by=Message.created_at.asc(),
        )

    async def count_session_messages(self, session_id: str) -> int:
        """Count messages for a specific session."""
        return await self.count(session_id=session_id)

    async def get_recent_messages(
        self,
        session_id: str,
        limit: int = 10,
    ) -> list[Message]:
        """Get the most recent messages for context retrieval."""
        result = await self.db.execute(
            select(Message)
            .where(Message.session_id == session_id)
            .order_by(Message.created_at.desc())
            .limit(limit)
        )
        messages = list(result.scalars().all())
        messages.reverse()
        return messages

    async def get_messages_after(
        self,
        session_id: str,
        after_message_id: str,
    ) -> list[Message]:
        """Get messages created after a specific message (by creation time)."""
        # First get the reference message's created_at
        ref_result = await self.db.execute(
            select(Message.created_at).where(Message.id == after_message_id)
        )
        ref_time = ref_result.scalar_one_or_none()
        if ref_time is None:
            # If reference message not found, return all messages
            return await self.get_session_messages(session_id)

        result = await self.db.execute(
            select(Message)
            .where(
                Message.session_id == session_id,
                Message.created_at > ref_time,
            )
            .order_by(Message.created_at.asc())
        )
        return list(result.scalars().all())

    async def create_message(
        self,
        session_id: str,
        role: str,
        content: str,
        metadata: dict[str, Any] | None = None,
    ) -> Message:
        """Create a new message."""
        message = Message(
            session_id=session_id,
            role=role,
            content=content,
            metadata_=metadata,
        )
        return await self.create(message)
