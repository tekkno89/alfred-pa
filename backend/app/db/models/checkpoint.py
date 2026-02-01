from typing import Any

from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class Checkpoint(Base, TimestampMixin):
    """LangGraph checkpoint for state persistence."""

    __tablename__ = "checkpoints"

    thread_id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True)
    checkpoint: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)

    def __repr__(self) -> str:
        return f"<Checkpoint(thread_id={self.thread_id})>"
