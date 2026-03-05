"""Todo model for task management."""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.db.models.user import User


class Todo(Base, UUIDMixin, TimestampMixin):
    """User todo/task with priority, due date, recurrence, and reminders."""

    __tablename__ = "todos"

    user_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("users.id"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    priority: Mapped[int] = mapped_column(
        Integer, default=2, server_default="2"
    )  # 0=Urgent, 1=High, 2=Medium, 3=Low
    status: Mapped[str] = mapped_column(
        String(20), default="open", server_default="open"
    )  # "open" | "completed"
    due_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    is_starred: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false"
    )
    tags: Mapped[list[str]] = mapped_column(
        ARRAY(String(100)), default=list, server_default="{}"
    )
    recurrence_rule: Mapped[str | None] = mapped_column(
        String(500), nullable=True
    )  # RFC 5545 RRULE
    recurrence_parent_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False), ForeignKey("todos.id"), nullable=True
    )
    reminder_sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    reminder_job_id: Mapped[str | None] = mapped_column(
        String(100), nullable=True
    )
    slack_reminder_thread_ts: Mapped[str | None] = mapped_column(
        String(50), nullable=True
    )
    slack_reminder_channel: Mapped[str | None] = mapped_column(
        String(50), nullable=True
    )

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="todos")
    recurrence_parent: Mapped["Todo | None"] = relationship(
        "Todo", remote_side="Todo.id", foreign_keys=[recurrence_parent_id]
    )

    def __repr__(self) -> str:
        return f"<Todo(id={self.id}, title={self.title!r}, status={self.status})>"
