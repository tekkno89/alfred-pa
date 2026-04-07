from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.db.models.user import User


class UserRepo(Base, UUIDMixin, TimestampMixin):
    """User-registered repository for short-name resolution."""

    __tablename__ = "user_repos"
    __table_args__ = (
        UniqueConstraint(
            "user_id", "owner", "repo_name",
            name="uq_user_repos_user_owner_repo",
        ),
        Index("ix_user_repos_user_repo_name", "user_id", "repo_name"),
        Index("ix_user_repos_user_alias", "user_id", "alias"),
    )

    user_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("users.id"), nullable=False
    )
    owner: Mapped[str] = mapped_column(String(255), nullable=False)
    repo_name: Mapped[str] = mapped_column(String(255), nullable=False)
    alias: Mapped[str | None] = mapped_column(String(100), nullable=True)
    github_account_label: Mapped[str | None] = mapped_column(
        String(100), nullable=True
    )

    # Relationships
    user: Mapped["User"] = relationship("User")

    @property
    def full_name(self) -> str:
        return f"{self.owner}/{self.repo_name}"

    def __repr__(self) -> str:
        return f"<UserRepo(id={self.id}, full_name={self.full_name!r}, alias={self.alias!r})>"
