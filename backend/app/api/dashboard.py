"""Dashboard API endpoints."""

from fastapi import APIRouter, HTTPException, Query, status

from app.api.deps import CurrentUser, DbSession
from app.db.repositories.dashboard import (
    DashboardPreferenceRepository,
    FeatureAccessRepository,
)
from app.schemas.dashboard import (
    BartDepartureResponse,
    BartStationsResponse,
    DashboardPreferenceList,
    DashboardPreferenceResponse,
    DashboardPreferenceUpdate,
)
from app.services.bart import BartService

router = APIRouter()


# --- BART proxy endpoints ---


@router.get("/bart/departures", response_model=BartDepartureResponse)
async def get_bart_departures(
    user: CurrentUser,
    db: DbSession,
    station: str = Query(..., description="Station abbreviation (e.g. EMBR)"),
    platform: int | None = Query(None, description="Platform filter"),
) -> BartDepartureResponse:
    """Get real-time BART departures for a station."""
    # Check feature access
    repo = FeatureAccessRepository(db)
    if user.role != "admin" and not await repo.is_enabled(user.id, "card:bart"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="BART card access not enabled",
        )

    service = BartService()
    return await service.get_departures(station, platform)


@router.get("/bart/stations", response_model=BartStationsResponse)
async def get_bart_stations(
    user: CurrentUser,
) -> BartStationsResponse:
    """Get list of all BART stations."""
    service = BartService()
    return await service.get_stations()


# --- Available cards endpoint ---


@router.get("/available-cards", response_model=list[str])
async def get_available_cards(
    user: CurrentUser,
    db: DbSession,
) -> list[str]:
    """Return card types the current user has access to."""
    cards: list[str] = []
    repo = FeatureAccessRepository(db)
    if await repo.is_enabled(user.id, "card:bart"):
        cards.append("bart")
    return cards


# --- Dashboard preference endpoints ---


@router.get("/preferences", response_model=DashboardPreferenceList)
async def get_preferences(
    user: CurrentUser,
    db: DbSession,
) -> DashboardPreferenceList:
    """Get the current user's dashboard card preferences."""
    repo = DashboardPreferenceRepository(db)
    prefs = await repo.get_by_user(user.id)
    return DashboardPreferenceList(
        items=[DashboardPreferenceResponse.model_validate(p) for p in prefs]
    )


@router.put("/preferences/{card_type}", response_model=DashboardPreferenceResponse)
async def upsert_preference(
    card_type: str,
    data: DashboardPreferenceUpdate,
    user: CurrentUser,
    db: DbSession,
) -> DashboardPreferenceResponse:
    """Create or update a dashboard card preference."""
    repo = DashboardPreferenceRepository(db)
    pref = await repo.upsert(user.id, card_type, data.preferences, data.sort_order)
    return DashboardPreferenceResponse.model_validate(pref)


@router.delete("/preferences/{card_type}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_preference(
    card_type: str,
    user: CurrentUser,
    db: DbSession,
) -> None:
    """Remove a dashboard card preference."""
    repo = DashboardPreferenceRepository(db)
    deleted = await repo.delete_by_user_and_card(user.id, card_type)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Card preference not found",
        )
