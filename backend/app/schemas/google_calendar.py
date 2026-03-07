"""Google Calendar integration schemas for request/response validation."""

from datetime import datetime

from pydantic import BaseModel


class GoogleCalendarOAuthUrlResponse(BaseModel):
    """Response containing the Google Calendar OAuth URL."""

    url: str


class GoogleCalendarConnectionResponse(BaseModel):
    """Response for a single Google Calendar connection."""

    model_config = {"from_attributes": True}

    id: str
    provider: str
    account_label: str
    external_account_id: str | None = None
    token_type: str
    scope: str | None = None
    expires_at: datetime | None = None
    created_at: datetime


class GoogleCalendarConnectionListResponse(BaseModel):
    """Response listing all Google Calendar connections."""

    connections: list[GoogleCalendarConnectionResponse]
