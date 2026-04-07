"""Coding job model for Claude Code container orchestration."""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.db.models.session import Session
    from app.db.models.user import User


class CodingJob(Base, UUIDMixin, TimestampMixin):
    """Tracks Claude Code container jobs for coding assistance.

    Status flow:
      pending_plan_approval → planning → plan_ready
        → pending_impl_approval → implementing → reviewing → complete
      Any status → failed | cancelled
      exploring (standalone for ask_codebase)
    """

    __tablename__ = "coding_jobs"

    user_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("users.id"), nullable=False
    )
    session_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("sessions.id"), nullable=False
    )
    status: Mapped[str] = mapped_column(
        String(30), default="pending_plan_approval", nullable=False
    )
    mode: Mapped[str] = mapped_column(
        String(20), default="plan", nullable=False
    )  # plan | implement | review | explore

    # Repository info
    repo_full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    branch_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    pr_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    pr_number: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Task details
    task_description: Mapped[str] = mapped_column(Text, nullable=False)
    plan_content: Mapped[str | None] = mapped_column(Text, nullable=True)
    review_content: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Revision chain
    revision_of_job_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False), ForeignKey("coding_jobs.id"), nullable=True
    )

    # Container tracking
    container_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    runtime_type: Mapped[str | None] = mapped_column(
        String(30), default="docker_sandbox", nullable=True
    )
    error_details: Mapped[str | None] = mapped_column(Text, nullable=True)

    # GitHub connection
    github_account_label: Mapped[str | None] = mapped_column(
        String(100), nullable=True
    )

    # Audit trail
    conversation_log: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Slack thread for status updates
    slack_channel_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    slack_thread_ts: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # Timing
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Relationships
    user: Mapped["User"] = relationship("User")
    session: Mapped["Session"] = relationship("Session")
    revision_of: Mapped["CodingJob | None"] = relationship(
        "CodingJob", remote_side="CodingJob.id", foreign_keys=[revision_of_job_id]
    )

    def __repr__(self) -> str:
        return f"<CodingJob(id={self.id}, repo={self.repo_full_name}, status={self.status})>"
