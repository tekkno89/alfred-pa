"""Away mode API endpoints for triage system."""

import logging

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from app.api.deps import CurrentUser, DbSession
from app.db.repositories import FeatureAccessRepository
from app.db.repositories.triage import (
    TriageClassificationRepository,
    TriageUserSettingsRepository,
)
from app.schemas.triage import TriageSettingsResponse

logger = logging.getLogger(__name__)

router = APIRouter()


class AwayModeToggleRequest(BaseModel):
    """Request to toggle away mode."""

    enabled: bool


class AwayModeToggleResponse(BaseModel):
    """Response after toggling away mode."""

    enabled: bool
    queued_count: int = 0


class AwayModeConfigureRequest(BaseModel):
    """Request to configure away mode behavior."""

    notify_now_behavior: str = Field(
        ..., pattern="^(push_immediately|queue_for_catchup)$"
    )


async def _check_triage_access(user_id: str, db, role: str) -> None:
    """Check if user has triage feature access."""
    repo = FeatureAccessRepository(db)
    if role != "admin" and not await repo.is_enabled(user_id, "card:triage"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Triage feature not enabled",
        )


@router.post("/toggle", response_model=AwayModeToggleResponse)
async def toggle_away_mode(
    data: AwayModeToggleRequest,
    current_user: CurrentUser,
    db: DbSession,
) -> AwayModeToggleResponse:
    """Toggle away mode on/off.

    When toggled OFF, delivers catch-up digest via Slack DM if items are queued.
    """
    await _check_triage_access(current_user.id, db, current_user.role)

    settings_repo = TriageUserSettingsRepository(db)
    class_repo = TriageClassificationRepository(db)

    settings = await settings_repo.get_or_create(current_user.id)

    if data.enabled == settings.away_mode_enabled:
        return AwayModeToggleResponse(
            enabled=settings.away_mode_enabled,
            queued_count=0,
        )

    settings = await settings_repo.update(settings, away_mode_enabled=data.enabled)

    queued_count = 0
    if not data.enabled:
        queued_items = await class_repo.get_unalerted_all_priorities(current_user.id)
        queued_count = len(queued_items)

        if queued_count > 0:
            from app.services.triage_delivery import TriageDeliveryService

            try:
                delivery_svc = TriageDeliveryService(db)
                await delivery_svc._send_digest_dm(
                    current_user.id,
                    queued_items,
                    "Catch-Up Digest",
                )

                ids = [item.id for item in queued_items]
                await class_repo.clear_queued_for_digest(ids, current_user.id)
                await db.commit()
            except Exception:
                logger.exception(
                    f"Failed to send catch-up digest for user={current_user.id}"
                )

    return AwayModeToggleResponse(
        enabled=settings.away_mode_enabled,
        queued_count=queued_count,
    )


@router.post("/configure", response_model=TriageSettingsResponse)
async def configure_away_mode(
    data: AwayModeConfigureRequest,
    current_user: CurrentUser,
    db: DbSession,
) -> TriageSettingsResponse:
    """Configure away mode behavior."""
    await _check_triage_access(current_user.id, db, current_user.role)

    settings_repo = TriageUserSettingsRepository(db)
    settings = await settings_repo.get_or_create(current_user.id)

    settings = await settings_repo.update(
        settings,
        away_mode_notify_now_behavior=data.notify_now_behavior,
    )

    return TriageSettingsResponse.model_validate(settings)
