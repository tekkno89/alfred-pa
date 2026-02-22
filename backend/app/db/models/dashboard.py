"""Dashboard models for user preferences and feature access."""

from typing import TYPE_CHECKING

from sqlalchemy import Boolean, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.db.models.user import User


class UserDashboardPreference(Base, UUIDMixin, TimestampMixin):
    """Per-card dashboard preferences for a user."""

    __tablename__ = "user_dashboard_preferences"
    __table_args__ = (
        UniqueConstraint("user_id", "card_type", name="uq_user_dashboard_preferences_user_card"),
    )

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    card_type: Mapped[str] = mapped_column(String(50), nullable=False)
    preferences: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="dashboard_preferences")

    def __repr__(self) -> str:
        return f"<UserDashboardPreference(user_id={self.user_id}, card_type={self.card_type})>"


class UserFeatureAccess(Base, UUIDMixin, TimestampMixin):
    """Feature access control per user."""

    __tablename__ = "user_feature_access"
    __table_args__ = (
        UniqueConstraint("user_id", "feature_key", name="uq_user_feature_access_user_feature"),
    )

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    feature_key: Mapped[str] = mapped_column(String(100), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    granted_by: Mapped[str | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="feature_access", foreign_keys=[user_id])

    def __repr__(self) -> str:
        return f"<UserFeatureAccess(user_id={self.user_id}, feature_key={self.feature_key}, enabled={self.enabled})>"
