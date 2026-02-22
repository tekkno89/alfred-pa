from typing import TYPE_CHECKING

from sqlalchemy import Boolean, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.db.models.user import User


class Note(Base, UUIDMixin, TimestampMixin):
    """User notes with markdown support."""

    __tablename__ = "notes"

    user_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("users.id"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(500), default="", server_default="")
    body: Mapped[str] = mapped_column(Text, default="", server_default="")
    is_favorited: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false"
    )
    is_archived: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false"
    )
    tags: Mapped[list[str]] = mapped_column(
        ARRAY(String(100)), default=list, server_default="{}"
    )

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="notes")

    def __repr__(self) -> str:
        return f"<Note(id={self.id}, title={self.title!r})>"
