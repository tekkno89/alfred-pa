"""Coding job repository."""

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.coding_job import CodingJob
from app.db.repositories.base import BaseRepository

# Terminal statuses — jobs in these states cannot be advanced
TERMINAL_STATUSES = {"complete", "failed", "cancelled"}

# Active statuses — jobs currently running or awaiting action
ACTIVE_STATUSES = {
    "pending_plan_approval",
    "planning",
    "plan_ready",
    "pending_impl_approval",
    "implementing",
    "reviewing",
    "exploring",
}


class CodingJobRepository(BaseRepository[CodingJob]):
    """Repository for CodingJob model."""

    def __init__(self, db: AsyncSession):
        super().__init__(CodingJob, db)

    async def create_job(
        self,
        user_id: str,
        session_id: str,
        repo_full_name: str,
        task_description: str,
        *,
        mode: str = "plan",
        status: str = "pending_plan_approval",
        github_account_label: str | None = None,
        revision_of_job_id: str | None = None,
        branch_name: str | None = None,
        pr_url: str | None = None,
        pr_number: int | None = None,
    ) -> CodingJob:
        """Create a new coding job."""
        job = CodingJob(
            user_id=user_id,
            session_id=session_id,
            repo_full_name=repo_full_name,
            task_description=task_description,
            mode=mode,
            status=status,
            github_account_label=github_account_label,
            revision_of_job_id=revision_of_job_id,
            branch_name=branch_name,
            pr_url=pr_url,
            pr_number=pr_number,
        )
        return await self.create(job)

    async def get_by_session(
        self, session_id: str, *, include_terminal: bool = False
    ) -> list[CodingJob]:
        """Get coding jobs for a session, optionally excluding terminal states."""
        query = select(CodingJob).where(CodingJob.session_id == session_id)
        if not include_terminal:
            query = query.where(CodingJob.status.in_(ACTIVE_STATUSES))
        query = query.order_by(CodingJob.created_at.desc())
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def get_active_by_user(self, user_id: str) -> list[CodingJob]:
        """Get all active (non-terminal) coding jobs for a user."""
        query = (
            select(CodingJob)
            .where(
                CodingJob.user_id == user_id,
                CodingJob.status.in_(ACTIVE_STATUSES),
            )
            .order_by(CodingJob.created_at.desc())
        )
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def count_active_by_user(self, user_id: str) -> int:
        """Count active coding jobs for a user (for rate limiting)."""
        query = (
            select(func.count())
            .select_from(CodingJob)
            .where(
                CodingJob.user_id == user_id,
                CodingJob.status.in_(ACTIVE_STATUSES),
            )
        )
        result = await self.db.execute(query)
        return result.scalar() or 0

    async def get_user_jobs(
        self,
        user_id: str,
        *,
        status: str | None = None,
        skip: int = 0,
        limit: int = 20,
    ) -> list[CodingJob]:
        """Get paginated coding jobs for a user."""
        query = select(CodingJob).where(CodingJob.user_id == user_id)
        if status is not None:
            query = query.where(CodingJob.status == status)
        query = query.order_by(CodingJob.created_at.desc()).offset(skip).limit(limit)
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def count_user_jobs(
        self, user_id: str, *, status: str | None = None
    ) -> int:
        """Count coding jobs for a user."""
        query = (
            select(func.count())
            .select_from(CodingJob)
            .where(CodingJob.user_id == user_id)
        )
        if status is not None:
            query = query.where(CodingJob.status == status)
        result = await self.db.execute(query)
        return result.scalar() or 0

    async def update_status(
        self, job: CodingJob, status: str, **extras: object
    ) -> CodingJob:
        """Update a job's status and optional extra fields."""
        return await self.update(job, status=status, **extras)

    async def mark_started(
        self,
        job: CodingJob,
        container_id: str,
        started_at: datetime,
        runtime_type: str = "docker_sandbox",
    ) -> CodingJob:
        """Mark a job as started with container info."""
        return await self.update(
            job,
            container_id=container_id,
            started_at=started_at,
            runtime_type=runtime_type,
        )

    async def mark_completed(
        self, job: CodingJob, completed_at: datetime, **extras: object
    ) -> CodingJob:
        """Mark a job as completed."""
        return await self.update(
            job, status="complete", completed_at=completed_at, **extras
        )
