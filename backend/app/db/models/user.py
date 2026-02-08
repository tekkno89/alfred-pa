from typing import TYPE_CHECKING

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.db.models.session import Session
    from app.db.models.memory import Memory
    from app.db.models.focus import FocusModeState, FocusSettings, FocusVIPList
    from app.db.models.webhook import WebhookSubscription
    from app.db.models.oauth_token import UserOAuthToken


class User(Base, UUIDMixin, TimestampMixin):
    """User model for authentication."""

    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    oauth_provider: Mapped[str | None] = mapped_column(String(50), nullable=True)
    oauth_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    slack_user_id: Mapped[str | None] = mapped_column(String(50), unique=True, nullable=True)

    # Relationships
    sessions: Mapped[list["Session"]] = relationship(
        "Session", back_populates="user", cascade="all, delete-orphan"
    )
    memories: Mapped[list["Memory"]] = relationship(
        "Memory", back_populates="user", cascade="all, delete-orphan"
    )
    focus_state: Mapped["FocusModeState | None"] = relationship(
        "FocusModeState", back_populates="user", uselist=False, cascade="all, delete-orphan"
    )
    focus_settings: Mapped["FocusSettings | None"] = relationship(
        "FocusSettings", back_populates="user", uselist=False, cascade="all, delete-orphan"
    )
    focus_vip_list: Mapped[list["FocusVIPList"]] = relationship(
        "FocusVIPList", back_populates="user", cascade="all, delete-orphan"
    )
    webhook_subscriptions: Mapped[list["WebhookSubscription"]] = relationship(
        "WebhookSubscription", back_populates="user", cascade="all, delete-orphan"
    )
    oauth_tokens: Mapped[list["UserOAuthToken"]] = relationship(
        "UserOAuthToken", back_populates="user", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<User(id={self.id}, email={self.email})>"
