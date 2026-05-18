"""Adaptive delivery windows API endpoints."""

from fastapi import APIRouter, HTTPException, status

from app.api.deps import CurrentUser, DbSession
from app.db.repositories import FeatureAccessRepository
from app.schemas.triage import (
    AdaptiveWindowList,
    AdaptiveWindowResetResponse,
    AdaptiveWindowResponse,
)
from app.services.adaptive_window_service import AdaptiveWindowService

router = APIRouter()


async def _check_triage_access(user_id: str, db, role: str) -> None:
    """Check if user has triage feature access."""
    repo = FeatureAccessRepository(db)
    if role != "admin" and not await repo.is_enabled(user_id, "card:triage"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Triage feature not enabled",
        )


@router.get("", response_model=AdaptiveWindowList)
async def list_adaptive_windows(
    current_user: CurrentUser,
    db: DbSession,
) -> AdaptiveWindowList:
    """List all adaptive windows for the current user."""
    await _check_triage_access(current_user.id, db, current_user.role)
    service = AdaptiveWindowService(db)
    windows = await service.get_all_windows(current_user.id)
    return AdaptiveWindowList(
        windows=[AdaptiveWindowResponse(**w) for w in windows]
    )


@router.post(
    "/{message_type_name}/reset",
    response_model=AdaptiveWindowResetResponse,
)
async def reset_adaptive_window(
    message_type_name: str,
    current_user: CurrentUser,
    db: DbSession,
) -> AdaptiveWindowResetResponse:
    """Reset an adaptive window to its starter value."""
    await _check_triage_access(current_user.id, db, current_user.role)
    service = AdaptiveWindowService(db)
    new_window = await service.reset_window(current_user.id, message_type_name)
    await db.commit()
    return AdaptiveWindowResetResponse(
        message_type_name=message_type_name,
        window_minutes=new_window,
        message=f"Window reset to starter value of {new_window} minutes",
    )
