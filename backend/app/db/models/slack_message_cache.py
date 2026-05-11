"""Slack message cache model for non-sensitive public channels."""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class SlackMessageCache(Base):
    """Workspace-scoped cache of raw message text for non-sensitive public channels.

    This is the ONLY place raw Slack message text is persisted.
    - Public non-sensitive channels: cached with 7-day TTL
    - Private channels: NOT cached (sensitive=true)
    - DMs: NOT cached (hardcoded, never stored)

    Multiple users monitoring the same channel share the same cache rows.
    """

    __tablename__ = "slack_message_cache"

    workspace_id: Mapped[str] = mapped_column(String(50), primary_key=True)
    channel_id: Mapped[str] = mapped_column(String(50), primary_key=True)
    message_ts: Mapped[str] = mapped_column(String(50), primary_key=True)
    parent_thread_ts: Mapped[str | None] = mapped_column(String(50), nullable=True)
    sender_slack_id: Mapped[str] = mapped_column(String(50), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    is_bot: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    cached_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    def __repr__(self) -> str:
        return f"<SlackMessageCache({self.channel_id}/{self.message_ts})>"
