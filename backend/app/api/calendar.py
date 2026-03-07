"""Calendar API endpoints for event management and preferences."""

import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException, Query, status

from app.api.deps import CurrentUser, DbSession
from app.db.repositories.dashboard import DashboardPreferenceRepository, FeatureAccessRepository
from app.schemas.calendar import (
    CalendarEventCreateRequest,
    CalendarEventListResponse,
    CalendarEventResponse,
    CalendarEventUpdateRequest,
    CalendarListResponse,
    CalendarPreferenceBulkUpdate,
    CalendarPreferenceItem,
    CalendarResponse,
)
from app.services.google_calendar import CALENDAR_COLOR_PALETTE, GoogleCalendarService

logger = logging.getLogger(__name__)

router = APIRouter()


async def _check_calendar_access(user, db) -> None:
    """Check if user has calendar feature access."""
    if user.role == "admin":
        return
    repo = FeatureAccessRepository(db)
    if not await repo.is_enabled(user.id, "card:calendar"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Calendar access not enabled",
        )


def _get_calendar_prefs(pref_data: dict | None) -> list[dict]:
    """Extract calendar preferences from dashboard preference data."""
    if not pref_data:
        return []
    return pref_data.get("calendars", [])


def _merge_calendars_with_prefs(
    calendars: list[dict], prefs: list[dict]
) -> list[CalendarResponse]:
    """Merge Google Calendar list with user preferences (color, visibility)."""
    pref_map = {
        (p["account_label"], p["calendar_id"]): p for p in prefs
    }

    result = []
    color_idx = 0

    for cal in calendars:
        key = (cal.get("account_label", "default"), cal["id"])
        pref = pref_map.get(key)

        if pref:
            color = pref.get("color", CALENDAR_COLOR_PALETTE[color_idx % len(CALENDAR_COLOR_PALETTE)])
            visible = pref.get("visible", True)
        else:
            color = CALENDAR_COLOR_PALETTE[color_idx % len(CALENDAR_COLOR_PALETTE)]
            visible = True

        result.append(CalendarResponse(
            id=cal["id"],
            name=cal.get("name", cal["id"]),
            description=cal.get("description"),
            primary=cal.get("primary", False),
            background_color=cal.get("background_color"),
            foreground_color=cal.get("foreground_color"),
            access_role=cal.get("access_role", "reader"),
            account_label=cal.get("account_label", "default"),
            account_email=cal.get("account_email"),
            color=color,
            visible=visible,
        ))
        color_idx += 1

    return result


@router.get("/calendars", response_model=CalendarListResponse)
async def list_calendars(user: CurrentUser, db: DbSession) -> CalendarListResponse:
    """List all calendars across connected accounts, merged with preferences."""
    await _check_calendar_access(user, db)

    service = GoogleCalendarService(db)
    calendars = await service.list_all_calendars_for_user(user.id)

    pref_repo = DashboardPreferenceRepository(db)
    pref = await pref_repo.get_by_user_and_card(user.id, "calendar")
    prefs = _get_calendar_prefs(pref.preferences if pref else None)

    merged = _merge_calendars_with_prefs(calendars, prefs)
    return CalendarListResponse(calendars=merged)


@router.put("/calendars/preferences", response_model=CalendarListResponse)
async def update_calendar_preferences(
    data: CalendarPreferenceBulkUpdate,
    user: CurrentUser,
    db: DbSession,
) -> CalendarListResponse:
    """Update visibility and colors for calendars."""
    await _check_calendar_access(user, db)

    pref_repo = DashboardPreferenceRepository(db)
    prefs_data = {
        "calendars": [item.model_dump() for item in data.calendars]
    }
    await pref_repo.upsert(user.id, "calendar", prefs_data)

    # Return updated calendar list
    service = GoogleCalendarService(db)
    calendars = await service.list_all_calendars_for_user(user.id)
    merged = _merge_calendars_with_prefs(
        calendars, [item.model_dump() for item in data.calendars]
    )
    return CalendarListResponse(calendars=merged)


async def _get_visible_calendar_configs(
    user_id: str, db
) -> list[dict]:
    """Get visible calendar configs from user preferences."""
    pref_repo = DashboardPreferenceRepository(db)
    pref = await pref_repo.get_by_user_and_card(user_id, "calendar")
    prefs = _get_calendar_prefs(pref.preferences if pref else None)

    if prefs:
        return [p for p in prefs if p.get("visible", True)]

    # No preferences yet — fetch all calendars and return all as visible
    service = GoogleCalendarService(db)
    calendars = await service.list_all_calendars_for_user(user_id)
    return [
        {
            "account_label": cal.get("account_label", "default"),
            "calendar_id": cal["id"],
            "color": CALENDAR_COLOR_PALETTE[i % len(CALENDAR_COLOR_PALETTE)],
        }
        for i, cal in enumerate(calendars)
    ]


@router.get("/events", response_model=CalendarEventListResponse)
async def list_events(
    user: CurrentUser,
    db: DbSession,
    time_min: str = Query(..., description="ISO 8601 start of range"),
    time_max: str = Query(..., description="ISO 8601 end of range"),
) -> CalendarEventListResponse:
    """List events for a date range across visible calendars."""
    await _check_calendar_access(user, db)

    configs = await _get_visible_calendar_configs(user.id, db)
    if not configs:
        return CalendarEventListResponse(events=[])

    service = GoogleCalendarService(db)
    events = await service.list_events_for_user(user.id, configs, time_min, time_max)
    return CalendarEventListResponse(
        events=[CalendarEventResponse(**e) for e in events]
    )


@router.get("/events/today", response_model=CalendarEventListResponse)
async def list_today_events(
    user: CurrentUser,
    db: DbSession,
    tz: str = Query("UTC", description="IANA timezone"),
) -> CalendarEventListResponse:
    """List today's events for the dashboard card."""
    await _check_calendar_access(user, db)

    try:
        user_tz = ZoneInfo(tz)
    except (KeyError, ValueError):
        user_tz = ZoneInfo("UTC")

    now = datetime.now(user_tz)
    start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0)
    end_of_day = start_of_day + timedelta(days=1)

    time_min = start_of_day.isoformat()
    time_max = end_of_day.isoformat()

    configs = await _get_visible_calendar_configs(user.id, db)
    if not configs:
        return CalendarEventListResponse(events=[])

    service = GoogleCalendarService(db)
    events = await service.list_events_for_user(user.id, configs, time_min, time_max)
    return CalendarEventListResponse(
        events=[CalendarEventResponse(**e) for e in events]
    )


def _build_google_event_body(req: CalendarEventCreateRequest) -> dict:
    """Build Google Calendar API event body from create request."""
    body: dict = {"summary": req.title}

    if req.description:
        body["description"] = req.description
    if req.location:
        body["location"] = req.location

    if req.all_day:
        body["start"] = {"date": req.start}
        body["end"] = {"date": req.end or req.start}
    else:
        body["start"] = {"dateTime": req.start}
        if req.end:
            body["end"] = {"dateTime": req.end}
        else:
            # Default to 1 hour duration
            from datetime import datetime as dt
            try:
                start_dt = dt.fromisoformat(req.start)
                end_dt = start_dt + timedelta(hours=1)
                body["end"] = {"dateTime": end_dt.isoformat()}
            except ValueError:
                body["end"] = {"dateTime": req.start}

    if req.attendees:
        body["attendees"] = [{"email": email} for email in req.attendees]

    if req.recurrence:
        body["recurrence"] = req.recurrence

    return body


@router.post("/events", response_model=CalendarEventResponse, status_code=status.HTTP_201_CREATED)
async def create_event(
    req: CalendarEventCreateRequest,
    user: CurrentUser,
    db: DbSession,
) -> CalendarEventResponse:
    """Create a new calendar event."""
    await _check_calendar_access(user, db)

    service = GoogleCalendarService(db)
    body = _build_google_event_body(req)
    event = await service.create_event(user.id, req.account_label, req.calendar_id, body)
    return CalendarEventResponse(**event)


@router.patch("/events/{event_id}", response_model=CalendarEventResponse)
async def update_event(
    event_id: str,
    req: CalendarEventUpdateRequest,
    user: CurrentUser,
    db: DbSession,
    calendar_id: str = Query("primary"),
    account_label: str = Query("default"),
) -> CalendarEventResponse:
    """Update an existing calendar event."""
    await _check_calendar_access(user, db)

    body: dict = {}
    if req.title is not None:
        body["summary"] = req.title
    if req.description is not None:
        body["description"] = req.description
    if req.location is not None:
        body["location"] = req.location
    if req.start is not None:
        if req.all_day:
            body["start"] = {"date": req.start}
        else:
            body["start"] = {"dateTime": req.start}
    if req.end is not None:
        if req.all_day:
            body["end"] = {"date": req.end}
        else:
            body["end"] = {"dateTime": req.end}
    if req.attendees is not None:
        body["attendees"] = [{"email": email} for email in req.attendees]
    if req.recurrence is not None:
        body["recurrence"] = req.recurrence

    service = GoogleCalendarService(db)
    event = await service.update_event(user.id, account_label, calendar_id, event_id, body)
    return CalendarEventResponse(**event)


@router.delete("/events/{event_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_event(
    event_id: str,
    user: CurrentUser,
    db: DbSession,
    calendar_id: str = Query("primary"),
    account_label: str = Query("default"),
) -> None:
    """Delete a calendar event."""
    await _check_calendar_access(user, db)

    service = GoogleCalendarService(db)
    await service.delete_event(user.id, account_label, calendar_id, event_id)
