"""OAuth token model for storing user OAuth credentials."""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.db.models.encryption_key import EncryptionKey
    from app.db.models.github_app_config import GitHubAppConfig
    from app.db.models.user import User


class UserOAuthToken(Base, UUIDMixin, TimestampMixin):
    """OAuth tokens for external service access."""

    __tablename__ = "user_oauth_tokens"
    __table_args__ = (
        UniqueConstraint(
            "user_id", "provider", "account_label",
            name="uq_user_oauth_tokens_user_provider_label",
        ),
    )

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    provider: Mapped[str] = mapped_column(String(50), nullable=False)  # 'slack', 'github'
    access_token: Mapped[str] = mapped_column(Text, nullable=False)
    refresh_token: Mapped[str | None] = mapped_column(Text, nullable=True)
    scope: Mapped[str | None] = mapped_column(Text, nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(nullable=True)

    # Encrypted token fields (envelope encryption)
    encrypted_access_token: Mapped[str | None] = mapped_column(Text, nullable=True)
    encrypted_refresh_token: Mapped[str | None] = mapped_column(Text, nullable=True)
    encryption_key_id: Mapped[str | None] = mapped_column(
        ForeignKey("encryption_keys.id"), nullable=True
    )

    # Multi-account support
    account_label: Mapped[str] = mapped_column(
        String(100), nullable=False, default="default"
    )
    external_account_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True
    )
    token_type: Mapped[str] = mapped_column(
        String(20), nullable=False, default="oauth"
    )  # "oauth" or "pat"

    # Per-user GitHub App config (nullable; NULL = global config or PAT)
    github_app_config_id: Mapped[str | None] = mapped_column(
        ForeignKey("github_app_configs.id", ondelete="SET NULL"), nullable=True
    )

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="oauth_tokens")
    encryption_key: Mapped["EncryptionKey | None"] = relationship("EncryptionKey")
    github_app_config: Mapped["GitHubAppConfig | None"] = relationship("GitHubAppConfig")

    def __repr__(self) -> str:
        return f"<UserOAuthToken(user_id={self.user_id}, provider={self.provider}, label={self.account_label})>"
