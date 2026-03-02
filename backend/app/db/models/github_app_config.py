"""GitHub App configuration model for per-user GitHub App credentials."""

from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.db.models.encryption_key import EncryptionKey
    from app.db.models.user import User


class GitHubAppConfig(Base, UUIDMixin, TimestampMixin):
    """Per-user GitHub App configuration with encrypted credentials."""

    __tablename__ = "github_app_configs"
    __table_args__ = (
        UniqueConstraint(
            "user_id", "label",
            name="uq_github_app_configs_user_label",
        ),
    )

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    label: Mapped[str] = mapped_column(String(100), nullable=False)
    client_id: Mapped[str] = mapped_column(String(255), nullable=False)
    encrypted_client_secret: Mapped[str] = mapped_column(Text, nullable=False)
    encryption_key_id: Mapped[str] = mapped_column(
        ForeignKey("encryption_keys.id"), nullable=False
    )
    github_app_id: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="github_app_configs")
    encryption_key: Mapped["EncryptionKey"] = relationship("EncryptionKey")

    def __repr__(self) -> str:
        return f"<GitHubAppConfig(user_id={self.user_id}, label={self.label})>"
