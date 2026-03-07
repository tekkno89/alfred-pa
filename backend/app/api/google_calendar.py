"""Google Calendar integration API endpoints."""

from fastapi import APIRouter, HTTPException, Query, status
from fastapi.responses import RedirectResponse

from app.api.deps import CurrentUser, DbSession
from app.core.config import get_settings
from app.core.oauth_state import consume_oauth_state
from app.db.repositories import OAuthTokenRepository
from app.schemas.google_calendar import (
    GoogleCalendarConnectionListResponse,
    GoogleCalendarConnectionResponse,
    GoogleCalendarOAuthUrlResponse,
)
from app.services.google_calendar import GoogleCalendarService

router = APIRouter()


@router.get("/oauth/url", response_model=GoogleCalendarOAuthUrlResponse)
async def get_google_calendar_oauth_url(
    current_user: CurrentUser,
    db: DbSession,
    account_label: str = Query(default="default"),
) -> GoogleCalendarOAuthUrlResponse:
    """Generate Google Calendar OAuth authorization URL."""
    service = GoogleCalendarService(db)

    try:
        url = service.get_oauth_url(current_user.id, account_label)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )

    return GoogleCalendarOAuthUrlResponse(url=url)


@router.get("/oauth/callback")
async def google_calendar_oauth_callback(
    code: str = Query(...),
    state: str = Query(...),
    db: DbSession = None,
) -> RedirectResponse:
    """Handle Google Calendar OAuth callback."""
    settings = get_settings()

    state_data = consume_oauth_state(state)
    if not state_data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired OAuth state",
        )

    user_id = state_data["user_id"]
    account_label = state_data.get("account_label", "default")

    service = GoogleCalendarService(db)

    try:
        token_data = await service.exchange_code(code)
        await service.store_oauth_token(
            user_id=user_id,
            token_data=token_data,
            account_label=account_label,
        )
    except ValueError as e:
        redirect_url = f"{settings.frontend_url}/settings/integrations?google_calendar_oauth=error&message={str(e)}"
        return RedirectResponse(url=redirect_url)

    redirect_url = (
        f"{settings.frontend_url}/settings/integrations?google_calendar_oauth=success"
    )
    return RedirectResponse(url=redirect_url)


@router.get("/connections", response_model=GoogleCalendarConnectionListResponse)
async def list_google_calendar_connections(
    current_user: CurrentUser,
    db: DbSession,
) -> GoogleCalendarConnectionListResponse:
    """List all Google Calendar connections for the current user."""
    token_repo = OAuthTokenRepository(db)
    tokens = await token_repo.get_all_by_user_and_provider(
        current_user.id, "google_calendar"
    )

    connections = [
        GoogleCalendarConnectionResponse(
            id=t.id,
            provider=t.provider,
            account_label=t.account_label,
            external_account_id=t.external_account_id,
            token_type=t.token_type,
            scope=t.scope,
            expires_at=t.expires_at,
            created_at=t.created_at,
        )
        for t in tokens
    ]

    return GoogleCalendarConnectionListResponse(connections=connections)


@router.delete(
    "/connections/{connection_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_google_calendar_connection(
    connection_id: str,
    current_user: CurrentUser,
    db: DbSession,
) -> None:
    """Remove a Google Calendar connection."""
    service = GoogleCalendarService(db)
    deleted = await service.delete_connection(connection_id, current_user.id)

    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Connection not found",
        )
