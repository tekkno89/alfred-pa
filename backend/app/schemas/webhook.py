"""Webhook schemas for request/response validation."""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field, HttpUrl


class WebhookEventType(str, Enum):
    """Webhook event types."""

    FOCUS_STARTED = "focus_started"
    FOCUS_ENDED = "focus_ended"
    FOCUS_BYPASS = "focus_bypass"
    POMODORO_WORK_STARTED = "pomodoro_work_started"
    POMODORO_BREAK_STARTED = "pomodoro_break_started"


class WebhookCreateRequest(BaseModel):
    """Request to create a webhook subscription."""

    name: str = Field(..., min_length=1, max_length=255)
    url: HttpUrl
    event_types: list[WebhookEventType] = Field(..., min_length=1)


class WebhookUpdateRequest(BaseModel):
    """Request to update a webhook subscription."""

    name: str | None = Field(None, min_length=1, max_length=255)
    url: HttpUrl | None = None
    enabled: bool | None = None
    event_types: list[WebhookEventType] | None = Field(None, min_length=1)


class WebhookResponse(BaseModel):
    """Response with webhook subscription info."""

    model_config = {"from_attributes": True}

    id: str
    name: str
    url: str
    enabled: bool
    event_types: list[str]
    created_at: datetime
    updated_at: datetime


class WebhookListResponse(BaseModel):
    """Response with list of webhooks."""

    webhooks: list[WebhookResponse]


class WebhookTestRequest(BaseModel):
    """Request to test a webhook."""

    event_type: WebhookEventType = WebhookEventType.FOCUS_BYPASS


class WebhookTestResponse(BaseModel):
    """Response from webhook test."""

    success: bool
    status_code: int | None = None
    error: str | None = None
