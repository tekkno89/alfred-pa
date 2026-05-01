"""Conversation summary model for grouped messages in digests."""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.db.models.triage import TriageClassification
    from app.db.models.user import User


class ConversationSummary(Base, UUIDMixin, TimestampMixin):
    """A grouped conversation within a digest (thread, DM, or channel messages)."""

    __tablename__ = "conversation_summaries"

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    
    conversation_type: Mapped[str] = mapped_column(String(20), nullable=False)
    channel_id: Mapped[str] = mapped_column(String(50), nullable=False)
    channel_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    thread_ts: Mapped[str | None] = mapped_column(String(50), nullable=True)
    
    abstract: Mapped[str] = mapped_column(Text, nullable=False)
    participants: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    message_count: Mapped[int] = mapped_column(Integer, nullable=False)
    priority_level: Mapped[str] = mapped_column(String(20), nullable=False)
    
    first_message_ts: Mapped[str] = mapped_column(String(50), nullable=False)
    slack_permalink: Mapped[str | None] = mapped_column(Text, nullable=True)
    
    digest_summary_id: Mapped[str | None] = mapped_column(
        ForeignKey("triage_classifications.id", ondelete="SET NULL"), nullable=True
    )
    
    first_message_at: Mapped[datetime | None] = mapped_column(nullable=True)
    last_message_at: Mapped[datetime | None] = mapped_column(nullable=True)
    
    reviewed_at: Mapped[datetime | None] = mapped_column(nullable=True)
    user_reacted_at: Mapped[datetime | None] = mapped_column(nullable=True)
    user_responded_at: Mapped[datetime | None] = mapped_column(nullable=True)
    
    user: Mapped["User"] = relationship("User")
    digest_summary: Mapped["TriageClassification | None"] = relationship(
        "TriageClassification", foreign_keys=[digest_summary_id]
    )
    messages: Mapped[list["TriageClassification"]] = relationship(
        "TriageClassification",
        foreign_keys="TriageClassification.conversation_summary_id",
        back_populates="conversation_summary",
    )

    def __repr__(self) -> str:
        return f"<ConversationSummary(id={self.id}, type={self.conversation_type}, messages={self.message_count})>"
