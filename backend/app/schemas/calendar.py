"""Calendar schemas for request/response validation."""

from pydantic import BaseModel, Field


class CalendarResponse(BaseModel):
    """A single calendar from Google Calendar."""

    id: str
    name: str
    description: str | None = None
    primary: bool = False
    background_color: str | None = None
    foreground_color: str | None = None
    access_role: str = "reader"
    account_label: str = "default"
    account_email: str | None = None
    # Merged from user preferences
    color: str = "#4285f4"
    visible: bool = True


class CalendarListResponse(BaseModel):
    """Response listing all calendars with preferences merged."""

    calendars: list[CalendarResponse]


class CalendarPreferenceItem(BaseModel):
    """A single calendar's preference config."""

    account_label: str
    calendar_id: str
    calendar_name: str = ""
    color: str = "#4285f4"
    visible: bool = True


class CalendarPreferenceBulkUpdate(BaseModel):
    """Bulk update calendar preferences."""

    calendars: list[CalendarPreferenceItem]


class CalendarEventAttendee(BaseModel):
    """An event attendee."""

    email: str
    response_status: str = "needsAction"


class CalendarEventResponse(BaseModel):
    """A single calendar event."""

    id: str
    calendar_id: str
    title: str
    description: str | None = None
    location: str | None = None
    start: str
    end: str | None = None
    all_day: bool = False
    color: str = "#4285f4"
    status: str = "confirmed"
    html_link: str | None = None
    attendees: list[CalendarEventAttendee] = []
    recurring_event_id: str | None = None
    recurrence: list[str] | None = None
    creator: str | None = None
    organizer: str | None = None
    account_label: str = "default"


class CalendarEventListResponse(BaseModel):
    """Response listing calendar events."""

    events: list[CalendarEventResponse]


class CalendarEventCreateRequest(BaseModel):
    """Request to create a calendar event."""

    title: str = Field(..., min_length=1)
    description: str | None = None
    location: str | None = None
    start: str = Field(..., description="ISO 8601 datetime or date for all-day")
    end: str | None = Field(None, description="ISO 8601 datetime or date for all-day")
    all_day: bool = False
    calendar_id: str = "primary"
    account_label: str = "default"
    attendees: list[str] = Field(default_factory=list, description="Email addresses")
    recurrence: list[str] | None = Field(None, description="RRULE strings")


class CalendarEventUpdateRequest(BaseModel):
    """Request to update a calendar event."""

    title: str | None = None
    description: str | None = None
    location: str | None = None
    start: str | None = None
    end: str | None = None
    all_day: bool | None = None
    attendees: list[str] | None = None
    recurrence: list[str] | None = None
