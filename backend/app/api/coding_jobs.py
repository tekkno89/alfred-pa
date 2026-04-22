"""Coding jobs API — button-driven approval endpoints + container callback.

These endpoints are the ONLY way to advance a coding job past approval gates.
The agent tool cannot call these directly.

The ``/callback`` endpoint is unauthenticated (no user JWT) — it uses
stateless HMAC verification so containers can report completion.
"""

import logging

from fastapi import APIRouter, Header, HTTPException, Query, status

from app.api.deps import CurrentUser, DbSession
from app.db.repositories.coding_job import CodingJobRepository
from app.db.session import async_session_maker
from app.schemas.coding_job import (
    CodingJobCallbackRequest,
    CodingJobList,
    CodingJobResponse,
    CodingJobRevisionRequest,
)
from app.services.coding_job import CodingJobService

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("", response_model=CodingJobList)
async def list_coding_jobs(
    current_user: CurrentUser,
    db: DbSession,
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    job_status: str | None = Query(None, alias="status"),
) -> CodingJobList:
    """List the current user's coding jobs (paginated)."""
    repo = CodingJobRepository(db)
    skip = (page - 1) * size
    jobs = await repo.get_user_jobs(
        current_user.id, status=job_status, skip=skip, limit=size
    )
    total = await repo.count_user_jobs(current_user.id, status=job_status)
    return CodingJobList(
        items=[CodingJobResponse.model_validate(j) for j in jobs],
        total=total,
        page=page,
        size=size,
    )


@router.get("/{job_id}", response_model=CodingJobResponse)
async def get_coding_job(
    job_id: str,
    current_user: CurrentUser,
    db: DbSession,
) -> CodingJobResponse:
    """Get details for a specific coding job."""
    repo = CodingJobRepository(db)
    job = await repo.get(job_id)
    if not job or job.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Coding job not found")
    return CodingJobResponse.model_validate(job)


@router.post(
    "/{job_id}/approve-plan",
    response_model=CodingJobResponse,
)
async def approve_plan(
    job_id: str,
    current_user: CurrentUser,
    db: DbSession,
) -> CodingJobResponse:
    """Gate 1: Approve and start planning phase."""
    repo = CodingJobRepository(db)
    job = await repo.get(job_id)
    if not job or job.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Coding job not found")

    service = CodingJobService(db)
    try:
        job = await service.start_planning(job_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return CodingJobResponse.model_validate(job)


@router.post(
    "/{job_id}/approve-impl",
    response_model=CodingJobResponse,
)
async def approve_implementation(
    job_id: str,
    current_user: CurrentUser,
    db: DbSession,
) -> CodingJobResponse:
    """Gate 2: Approve and start implementation phase."""
    repo = CodingJobRepository(db)
    job = await repo.get(job_id)
    if not job or job.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Coding job not found")

    service = CodingJobService(db)
    try:
        job = await service.start_implementation(job_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return CodingJobResponse.model_validate(job)


@router.post(
    "/{job_id}/request-revision",
    response_model=CodingJobResponse,
    status_code=status.HTTP_201_CREATED,
)
async def request_revision(
    job_id: str,
    data: CodingJobRevisionRequest,
    current_user: CurrentUser,
    db: DbSession,
) -> CodingJobResponse:
    """Request changes to a completed job — creates a new linked revision."""
    repo = CodingJobRepository(db)
    job = await repo.get(job_id)
    if not job or job.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Coding job not found")

    service = CodingJobService(db)
    try:
        new_job = await service.request_revision(job_id, data.description)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return CodingJobResponse.model_validate(new_job)


@router.post(
    "/{job_id}/cancel",
    response_model=CodingJobResponse,
)
async def cancel_coding_job(
    job_id: str,
    current_user: CurrentUser,
    db: DbSession,
) -> CodingJobResponse:
    """Cancel an active coding job."""
    repo = CodingJobRepository(db)
    job = await repo.get(job_id)
    if not job or job.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Coding job not found")

    service = CodingJobService(db)
    try:
        job = await service.cancel_job(job_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return CodingJobResponse.model_validate(job)


@router.post("/callback", status_code=status.HTTP_200_OK)
async def coding_job_callback(
    data: CodingJobCallbackRequest,
    x_callback_token: str = Header(...),
) -> dict:
    """Container completion callback — no user auth, HMAC-verified.

    Containers POST here when they finish (success or failure).
    Token is ``hmac_sha256(jwt_secret, job_id)`` — stateless verification.
    """
    from app.core.runtime.docker_sandbox import verify_callback_token

    if not verify_callback_token(data.job_id, x_callback_token):
        raise HTTPException(status_code=403, detail="Invalid callback token")

    async with async_session_maker() as db:
        try:
            service = CodingJobService(db)
            if data.success:
                await service.handle_container_complete(
                    data.job_id, data.output_files
                )
            else:
                await service.handle_container_failed(
                    data.job_id,
                    data.error or f"Container exited with code {data.exit_code}",
                    data.logs,
                )
            await db.commit()
        except Exception:
            await db.rollback()
            logger.exception(
                f"Error processing callback for job {data.job_id}"
            )
            raise HTTPException(
                status_code=500, detail="Internal error processing callback"
            )

    return {"status": "ok", "job_id": data.job_id}
