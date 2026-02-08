"""Focus mode schemas for request/response validation."""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class FocusModeEnum(str, Enum):
    """Focus mode types."""

    SIMPLE = "simple"
    POMODORO = "pomodoro"


class PomodoroPhaseEnum(str, Enum):
    """Pomodoro phase types."""

    WORK = "work"
    BREAK = "break"


# Focus Mode State
class FocusEnableRequest(BaseModel):
    """Request to enable focus mode."""

    duration_minutes: int | None = Field(None, ge=1, le=480)
    custom_message: str | None = None


class FocusPomodoroStartRequest(BaseModel):
    """Request to start pomodoro mode."""

    custom_message: str | None = None
    work_minutes: int | None = Field(None, ge=1, le=120)
    break_minutes: int | None = Field(None, ge=1, le=60)
    total_sessions: int | None = Field(None, ge=1, le=12)


class FocusStatusResponse(BaseModel):
    """Response with current focus status."""

    model_config = {"from_attributes": True}

    is_active: bool
    mode: str = "simple"
    started_at: datetime | None = None
    ends_at: datetime | None = None
    custom_message: str | None = None
    pomodoro_phase: str | None = None
    pomodoro_session_count: int = 0
    pomodoro_total_sessions: int | None = None
    pomodoro_work_minutes: int | None = None
    pomodoro_break_minutes: int | None = None
    time_remaining_seconds: int | None = None


# Focus Settings
class FocusSettingsUpdate(BaseModel):
    """Request to update focus settings."""

    default_message: str | None = None
    pomodoro_work_minutes: int | None = Field(None, ge=1, le=120)
    pomodoro_break_minutes: int | None = Field(None, ge=1, le=60)


class FocusSettingsResponse(BaseModel):
    """Response with focus settings."""

    model_config = {"from_attributes": True}

    default_message: str | None = None
    pomodoro_work_minutes: int = 25
    pomodoro_break_minutes: int = 5


# VIP List
class VIPAddRequest(BaseModel):
    """Request to add a VIP user."""

    slack_user_id: str = Field(..., min_length=1)
    display_name: str | None = None


class VIPResponse(BaseModel):
    """Response with VIP user info."""

    model_config = {"from_attributes": True}

    id: str
    slack_user_id: str
    display_name: str | None = None
    created_at: datetime


class VIPListResponse(BaseModel):
    """Response with list of VIP users."""

    vips: list[VIPResponse]
