"""Webhook subscription model."""

from typing import TYPE_CHECKING

from sqlalchemy import Boolean, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.db.models.user import User


class WebhookSubscription(Base, UUIDMixin, TimestampMixin):
    """Webhook subscription for receiving events."""

    __tablename__ = "webhook_subscriptions"

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    url: Mapped[str] = mapped_column(String(2048), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    event_types: Mapped[list[str]] = mapped_column(JSON, nullable=False)

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="webhook_subscriptions")

    def __repr__(self) -> str:
        return f"<WebhookSubscription(id={self.id}, name={self.name})>"
