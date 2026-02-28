"""Focus mode models."""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.db.models.user import User


class FocusModeState(Base, UUIDMixin, TimestampMixin):
    """Focus mode state for a user."""

    __tablename__ = "focus_mode_state"

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=False)
    mode: Mapped[str] = mapped_column(String(20), default="simple")  # 'simple' | 'pomodoro'
    started_at: Mapped[datetime | None] = mapped_column(nullable=True)
    ends_at: Mapped[datetime | None] = mapped_column(nullable=True)
    custom_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    previous_slack_status: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    pomodoro_phase: Mapped[str | None] = mapped_column(String(20), nullable=True)  # 'work' | 'break'
    pomodoro_session_count: Mapped[int] = mapped_column(Integer, default=0)
    pomodoro_total_sessions: Mapped[int | None] = mapped_column(Integer, nullable=True)
    pomodoro_work_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    pomodoro_break_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="focus_state")

    def __repr__(self) -> str:
        return f"<FocusModeState(user_id={self.user_id}, is_active={self.is_active})>"


class FocusSettings(Base, UUIDMixin, TimestampMixin):
    """Focus mode settings for a user."""

    __tablename__ = "focus_settings"

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False, unique=True)
    default_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    pomodoro_work_minutes: Mapped[int] = mapped_column(Integer, default=25)
    pomodoro_break_minutes: Mapped[int] = mapped_column(Integer, default=5)
    bypass_notification_config: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # Slack status customization
    slack_status_text: Mapped[str | None] = mapped_column(String(100), nullable=True)
    slack_status_emoji: Mapped[str | None] = mapped_column(String(50), nullable=True)
    pomodoro_work_status_text: Mapped[str | None] = mapped_column(String(100), nullable=True)
    pomodoro_work_status_emoji: Mapped[str | None] = mapped_column(String(50), nullable=True)
    pomodoro_break_status_text: Mapped[str | None] = mapped_column(String(100), nullable=True)
    pomodoro_break_status_emoji: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="focus_settings")

    def __repr__(self) -> str:
        return f"<FocusSettings(user_id={self.user_id})>"


class FocusVIPList(Base, UUIDMixin):
    """VIP users who can bypass focus mode."""

    __tablename__ = "focus_vip_list"

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    slack_user_id: Mapped[str] = mapped_column(String(50), nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="focus_vip_list")

    def __repr__(self) -> str:
        return f"<FocusVIPList(user_id={self.user_id}, slack_user_id={self.slack_user_id})>"
