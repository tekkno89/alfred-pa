from typing import TYPE_CHECKING

from pgvector.sqlalchemy import Vector
from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.db.models.user import User
    from app.db.models.session import Session


class Memory(Base, UUIDMixin, TimestampMixin):
    """Long-term memory model with vector embeddings."""

    __tablename__ = "memories"

    user_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("users.id"), nullable=False
    )
    type: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # 'preference' | 'knowledge' | 'summary'
    content: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[list[float] | None] = mapped_column(
        Vector(1536), nullable=True  # OpenAI embedding dimension
    )
    source_session_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False), ForeignKey("sessions.id"), nullable=True
    )

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="memories")
    source_session: Mapped["Session | None"] = relationship(
        "Session", back_populates="memories"
    )

    def __repr__(self) -> str:
        return f"<Memory(id={self.id}, type={self.type})>"
