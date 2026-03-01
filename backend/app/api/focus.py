"""Focus mode API endpoints."""

import logging

from fastapi import APIRouter, HTTPException, status

from app.api.deps import CurrentUser, DbSession
from app.db.repositories import FocusSettingsRepository, FocusVIPListRepository
from app.schemas.focus import (
    BypassNotificationConfig,
    FocusEnableRequest,
    FocusPomodoroStartRequest,
    FocusSettingsResponse,
    FocusSettingsUpdate,
    FocusStatusResponse,
    VIPAddRequest,
    VIPListResponse,
    VIPResponse,
)
from app.services.focus_orchestrator import FocusModeOrchestrator

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/enable", response_model=FocusStatusResponse)
async def enable_focus_mode(
    data: FocusEnableRequest,
    current_user: CurrentUser,
    db: DbSession,
) -> FocusStatusResponse:
    """
    Enable focus mode for the current user.

    Optionally set a duration (auto-disable) and custom message.
    """
    orchestrator = FocusModeOrchestrator(db)
    return await orchestrator.enable(
        user_id=current_user.id,
        duration_minutes=data.duration_minutes,
        custom_message=data.custom_message,
    )


@router.post("/disable", response_model=FocusStatusResponse)
async def disable_focus_mode(
    current_user: CurrentUser,
    db: DbSession,
) -> FocusStatusResponse:
    """Disable focus mode for the current user."""
    orchestrator = FocusModeOrchestrator(db)
    return await orchestrator.disable(user_id=current_user.id)


@router.get("/status", response_model=FocusStatusResponse)
async def get_focus_status(
    current_user: CurrentUser,
    db: DbSession,
) -> FocusStatusResponse:
    """Get current focus mode status."""
    orchestrator = FocusModeOrchestrator(db)
    return await orchestrator.get_status(user_id=current_user.id)


@router.post("/pomodoro/start", response_model=FocusStatusResponse)
async def start_pomodoro(
    data: FocusPomodoroStartRequest,
    current_user: CurrentUser,
    db: DbSession,
) -> FocusStatusResponse:
    """Start pomodoro mode."""
    orchestrator = FocusModeOrchestrator(db)
    return await orchestrator.start_pomodoro(
        user_id=current_user.id,
        custom_message=data.custom_message,
        work_minutes=data.work_minutes,
        break_minutes=data.break_minutes,
        total_sessions=data.total_sessions,
    )


@router.post("/pomodoro/skip", response_model=FocusStatusResponse)
async def skip_pomodoro_phase(
    current_user: CurrentUser,
    db: DbSession,
) -> FocusStatusResponse:
    """Skip to the next pomodoro phase (work/break), or end if all sessions complete."""
    orchestrator = FocusModeOrchestrator(db)
    return await orchestrator.skip_pomodoro_phase(user_id=current_user.id)


# Focus Settings endpoints
@router.get("/settings", response_model=FocusSettingsResponse)
async def get_focus_settings(
    current_user: CurrentUser,
    db: DbSession,
) -> FocusSettingsResponse:
    """Get focus mode settings."""
    settings_repo = FocusSettingsRepository(db)
    settings = await settings_repo.get_or_create(current_user.id)
    response = FocusSettingsResponse.model_validate(settings)

    # Apply defaults if bypass_notification_config is not set
    if response.bypass_notification_config is None and settings.bypass_notification_config is None:
        response.bypass_notification_config = BypassNotificationConfig()

    return response


@router.put("/settings", response_model=FocusSettingsResponse)
async def update_focus_settings(
    data: FocusSettingsUpdate,
    current_user: CurrentUser,
    db: DbSession,
) -> FocusSettingsResponse:
    """Update focus mode settings."""
    settings_repo = FocusSettingsRepository(db)
    settings = await settings_repo.get_or_create(current_user.id)

    updates = data.model_dump(exclude_unset=True)

    # Serialize bypass_notification_config to dict for JSON storage
    if "bypass_notification_config" in updates and updates["bypass_notification_config"] is not None:
        updates["bypass_notification_config"] = data.bypass_notification_config.model_dump()

    if updates:
        settings = await settings_repo.update(settings, **updates)

    return FocusSettingsResponse.model_validate(settings)


# VIP List endpoints
@router.get("/vip", response_model=VIPListResponse)
async def list_vip_users(
    current_user: CurrentUser,
    db: DbSession,
) -> VIPListResponse:
    """Get list of VIP users who bypass focus mode."""
    vip_repo = FocusVIPListRepository(db)
    vips = await vip_repo.get_by_user_id(current_user.id)
    return VIPListResponse(
        vips=[VIPResponse.model_validate(v) for v in vips]
    )


@router.post("/vip", response_model=VIPResponse, status_code=status.HTTP_201_CREATED)
async def add_vip_user(
    data: VIPAddRequest,
    current_user: CurrentUser,
    db: DbSession,
) -> VIPResponse:
    """Add a VIP user who can bypass focus mode."""
    vip_repo = FocusVIPListRepository(db)

    # Check if already exists
    if await vip_repo.is_vip(current_user.id, data.slack_user_id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User is already in VIP list",
        )

    vip = await vip_repo.add_vip(
        user_id=current_user.id,
        slack_user_id=data.slack_user_id,
        display_name=data.display_name,
    )
    return VIPResponse.model_validate(vip)


@router.delete("/vip/{vip_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_vip_user(
    vip_id: str,
    current_user: CurrentUser,
    db: DbSession,
) -> None:
    """Remove a VIP user."""
    vip_repo = FocusVIPListRepository(db)
    vip = await vip_repo.get(vip_id)

    if not vip or vip.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="VIP not found",
        )

    await vip_repo.delete(vip)
