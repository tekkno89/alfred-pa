"""Slack search models for channel participation and summaries."""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.db.models.user import User


class UserChannelParticipation(Base, UUIDMixin, TimestampMixin):
    """Per-user ranked list of most-active Slack channels."""

    __tablename__ = "user_channel_participation"

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    channel_id: Mapped[str] = mapped_column(String(50), nullable=False)
    channel_name: Mapped[str] = mapped_column(String(255), nullable=False)
    channel_type: Mapped[str] = mapped_column(String(10), nullable=False)  # public/private/mpim/im
    participation_rank: Mapped[int] = mapped_column(Integer, nullable=False)
    is_member: Mapped[bool] = mapped_column(Boolean, default=True)
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False)
    member_count: Mapped[int] = mapped_column(Integer, default=0)
    last_activity_at: Mapped[datetime | None] = mapped_column(nullable=True)

    # Relationships
    user: Mapped["User"] = relationship("User")

    __table_args__ = (
        UniqueConstraint("user_id", "channel_id", name="uq_user_channel_participation"),
    )

    def __repr__(self) -> str:
        return f"<UserChannelParticipation(user_id={self.user_id}, channel={self.channel_name}, rank={self.participation_rank})>"


class SlackChannelSummary(Base, UUIDMixin, TimestampMixin):
    """LLM-generated channel conversation summaries."""

    __tablename__ = "slack_channel_summaries"

    channel_id: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    channel_name: Mapped[str] = mapped_column(String(255), nullable=False)
    channel_type: Mapped[str] = mapped_column(String(10), nullable=False)  # public/private/mpim
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    member_count: Mapped[int] = mapped_column(Integer, default=0)
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False)
    generated_by_user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id"), nullable=False
    )
    last_summarized_at: Mapped[datetime] = mapped_column(nullable=False)

    # Relationships
    generated_by_user: Mapped["User"] = relationship("User")

    def __repr__(self) -> str:
        return f"<SlackChannelSummary(channel={self.channel_name}, type={self.channel_type})>"
