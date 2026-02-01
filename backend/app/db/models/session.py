from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.db.models.user import User
    from app.db.models.message import Message
    from app.db.models.memory import Memory


class Session(Base, UUIDMixin, TimestampMixin):
    """Conversation session model."""

    __tablename__ = "sessions"

    user_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("users.id"), nullable=False
    )
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source: Mapped[str] = mapped_column(String(50), nullable=False)  # 'webapp' | 'slack'
    slack_channel_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    slack_thread_ts: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="sessions")
    messages: Mapped[list["Message"]] = relationship(
        "Message", back_populates="session", cascade="all, delete-orphan"
    )
    memories: Mapped[list["Memory"]] = relationship(
        "Memory", back_populates="source_session"
    )

    def __repr__(self) -> str:
        return f"<Session(id={self.id}, source={self.source})>"
