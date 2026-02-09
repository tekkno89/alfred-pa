"""Focus mode API endpoints."""

import logging

from fastapi import APIRouter, HTTPException, status

from app.api.deps import CurrentUser, DbSession
from app.db.repositories import FocusSettingsRepository, FocusVIPListRepository
from app.schemas.focus import (
    FocusEnableRequest,
    FocusPomodoroStartRequest,
    FocusSettingsResponse,
    FocusSettingsUpdate,
    FocusStatusResponse,
    VIPAddRequest,
    VIPListResponse,
    VIPResponse,
)
from app.services.focus import FocusModeService
from app.services.notifications import NotificationService
from app.services.slack_user import SlackUserService
from app.worker.scheduler import (
    schedule_focus_expiration,
    cancel_focus_expiration,
    schedule_pomodoro_transition,
    cancel_pomodoro_transition,
)

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
    focus_service = FocusModeService(db)
    slack_user_service = SlackUserService(db)
    notification_service = NotificationService(db)

    # Save current Slack status before enabling focus mode
    previous_status = await slack_user_service.get_status(current_user.id)

    result = await focus_service.enable(
        user_id=current_user.id,
        duration_minutes=data.duration_minutes,
        custom_message=data.custom_message,
        previous_slack_status=previous_status,
    )

    # Set Slack status to focus mode
    focus_message = data.custom_message or "In focus mode"
    await slack_user_service.set_status(
        current_user.id,
        text=focus_message,
        emoji=":no_bell:",
    )

    # Enable Slack DND to prevent notifications
    # Use duration if set, otherwise default to 8 hours (480 min)
    dnd_duration = data.duration_minutes or 480
    await slack_user_service.enable_dnd(current_user.id, dnd_duration)

    # Publish focus started event
    await notification_service.publish(
        current_user.id,
        "focus_started",
        {
            "mode": "simple",
            "duration_minutes": data.duration_minutes,
            "custom_message": data.custom_message,
        },
    )

    # Schedule expiration job if duration is set
    if result.ends_at:
        await schedule_focus_expiration(current_user.id, result.ends_at)

    return result


@router.post("/disable", response_model=FocusStatusResponse)
async def disable_focus_mode(
    current_user: CurrentUser,
    db: DbSession,
) -> FocusStatusResponse:
    """Disable focus mode for the current user."""
    focus_service = FocusModeService(db)
    slack_user_service = SlackUserService(db)
    notification_service = NotificationService(db)

    # Cancel any scheduled expiration job
    await cancel_focus_expiration(current_user.id)
    await cancel_pomodoro_transition(current_user.id)

    # Get previous status before disabling
    previous_status = await focus_service.get_previous_slack_status(current_user.id)

    result = await focus_service.disable(current_user.id)

    # Restore previous Slack status
    if previous_status:
        await slack_user_service.set_status(
            current_user.id,
            text=previous_status.get("text", ""),
            emoji=previous_status.get("emoji", ""),
        )
    else:
        # Clear status if no previous status saved
        await slack_user_service.set_status(
            current_user.id,
            text="",
            emoji="",
        )

    # Disable Slack DND to restore notifications
    await slack_user_service.disable_dnd(current_user.id)

    # Publish focus ended event
    await notification_service.publish(
        current_user.id,
        "focus_ended",
        {},
    )

    return result


@router.get("/status", response_model=FocusStatusResponse)
async def get_focus_status(
    current_user: CurrentUser,
    db: DbSession,
) -> FocusStatusResponse:
    """Get current focus mode status."""
    focus_service = FocusModeService(db)
    slack_user_service = SlackUserService(db)
    notification_service = NotificationService(db)

    # Check if we need to expire the session
    previous_status = await focus_service.get_previous_slack_status(current_user.id)
    was_active = await focus_service.is_in_focus_mode(current_user.id)

    result = await focus_service.get_status(current_user.id)

    # If session was active but now isn't (expired), restore Slack status
    if was_active and not result.is_active:
        if previous_status:
            await slack_user_service.set_status(
                current_user.id,
                text=previous_status.get("text", ""),
                emoji=previous_status.get("emoji", ""),
            )
        else:
            await slack_user_service.set_status(
                current_user.id,
                text="",
                emoji="",
            )

        # Disable Slack DND
        await slack_user_service.disable_dnd(current_user.id)

        # Publish focus ended event
        await notification_service.publish(
            current_user.id,
            "focus_ended",
            {"reason": "expired"},
        )

    return result


@router.post("/pomodoro/start", response_model=FocusStatusResponse)
async def start_pomodoro(
    data: FocusPomodoroStartRequest,
    current_user: CurrentUser,
    db: DbSession,
) -> FocusStatusResponse:
    """Start pomodoro mode."""
    focus_service = FocusModeService(db)
    slack_user_service = SlackUserService(db)
    notification_service = NotificationService(db)

    # Save current Slack status before starting pomodoro
    previous_status = await slack_user_service.get_status(current_user.id)

    result = await focus_service.start_pomodoro(
        user_id=current_user.id,
        custom_message=data.custom_message,
        previous_slack_status=previous_status,
        work_minutes=data.work_minutes,
        break_minutes=data.break_minutes,
        total_sessions=data.total_sessions,
    )

    # Set Slack status for pomodoro
    await slack_user_service.set_status(
        current_user.id,
        text="Pomodoro - Focus time",
        emoji=":tomato:",
    )

    # Enable Slack DND during pomodoro work phase
    work_mins = data.work_minutes or 25
    await slack_user_service.enable_dnd(current_user.id, work_mins)

    # Publish event
    await notification_service.publish(
        current_user.id,
        "pomodoro_work_started",
        {"session_count": result.pomodoro_session_count},
    )

    # Schedule phase transition
    if result.ends_at:
        await schedule_pomodoro_transition(current_user.id, result.ends_at)

    return result


@router.post("/pomodoro/skip", response_model=FocusStatusResponse)
async def skip_pomodoro_phase(
    current_user: CurrentUser,
    db: DbSession,
) -> FocusStatusResponse:
    """Skip to the next pomodoro phase (work/break)."""
    focus_service = FocusModeService(db)
    slack_user_service = SlackUserService(db)
    notification_service = NotificationService(db)

    # Cancel current transition job
    await cancel_pomodoro_transition(current_user.id)

    result = await focus_service.skip_pomodoro_phase(current_user.id)

    # Update Slack status based on phase
    if result.pomodoro_phase == "work":
        await slack_user_service.set_status(
            current_user.id,
            text="Pomodoro - Focus time",
            emoji=":tomato:",
        )
        await notification_service.publish(
            current_user.id,
            "pomodoro_work_started",
            {"session_count": result.pomodoro_session_count},
        )
    else:
        await slack_user_service.set_status(
            current_user.id,
            text="Pomodoro - Break time",
            emoji=":coffee:",
        )
        await notification_service.publish(
            current_user.id,
            "pomodoro_break_started",
            {"session_count": result.pomodoro_session_count},
        )

    # Schedule next transition
    if result.ends_at:
        await schedule_pomodoro_transition(current_user.id, result.ends_at)

    return result


# Focus Settings endpoints
@router.get("/settings", response_model=FocusSettingsResponse)
async def get_focus_settings(
    current_user: CurrentUser,
    db: DbSession,
) -> FocusSettingsResponse:
    """Get focus mode settings."""
    settings_repo = FocusSettingsRepository(db)
    settings = await settings_repo.get_or_create(current_user.id)
    return FocusSettingsResponse.model_validate(settings)


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
