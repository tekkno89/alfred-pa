"""Focus mode schemas for request/response validation."""

from datetime import datetime, timezone
from enum import Enum
from typing import Annotated

from pydantic import BaseModel, Field, PlainSerializer, field_validator


# Custom serializer to ensure datetimes are serialized as UTC with Z suffix
def serialize_utc_datetime(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    # If naive datetime, assume UTC
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat().replace("+00:00", "Z")


UTCDatetime = Annotated[datetime | None, PlainSerializer(serialize_utc_datetime)]


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
    started_at: UTCDatetime = None
    ends_at: UTCDatetime = None
    custom_message: str | None = None
    pomodoro_phase: str | None = None
    pomodoro_session_count: int = 0
    pomodoro_total_sessions: int | None = None
    pomodoro_work_minutes: int | None = None
    pomodoro_break_minutes: int | None = None
    time_remaining_seconds: int | None = None


# Bypass Notification Config
class BypassNotificationConfig(BaseModel):
    """Configuration for how bypass notifications are delivered."""

    # Notification destinations
    alfred_ui_enabled: bool = True
    email_enabled: bool = False
    email_address: str | None = None
    sms_enabled: bool = False
    phone_number: str | None = None
    # Browser alert preferences (only relevant when alfred_ui_enabled)
    alert_sound_enabled: bool = True
    alert_sound_name: str = "chime"  # chime | urgent | gentle | ping
    alert_title_flash_enabled: bool = True


# Focus Settings
class FocusSettingsUpdate(BaseModel):
    """Request to update focus settings."""

    default_message: str | None = None
    pomodoro_work_minutes: int | None = Field(None, ge=1, le=120)
    pomodoro_break_minutes: int | None = Field(None, ge=1, le=60)
    bypass_notification_config: BypassNotificationConfig | None = None
    slack_status_text: str | None = Field(None, max_length=100)
    slack_status_emoji: str | None = Field(None, max_length=50)
    pomodoro_work_status_text: str | None = Field(None, max_length=100)
    pomodoro_work_status_emoji: str | None = Field(None, max_length=50)
    pomodoro_break_status_text: str | None = Field(None, max_length=100)
    pomodoro_break_status_emoji: str | None = Field(None, max_length=50)


_SLACK_STATUS_DEFAULTS: dict[str, str] = {
    "slack_status_text": "In focus mode",
    "slack_status_emoji": ":no_bell:",
    "pomodoro_work_status_text": "Pomodoro - Focus time",
    "pomodoro_work_status_emoji": ":tomato:",
    "pomodoro_break_status_text": "Pomodoro - Break time",
    "pomodoro_break_status_emoji": ":coffee:",
}


class FocusSettingsResponse(BaseModel):
    """Response with focus settings."""

    model_config = {"from_attributes": True}

    default_message: str | None = None
    pomodoro_work_minutes: int = 25
    pomodoro_break_minutes: int = 5
    bypass_notification_config: BypassNotificationConfig | None = None
    slack_status_text: str = "In focus mode"
    slack_status_emoji: str = ":no_bell:"
    pomodoro_work_status_text: str = "Pomodoro - Focus time"
    pomodoro_work_status_emoji: str = ":tomato:"
    pomodoro_break_status_text: str = "Pomodoro - Break time"
    pomodoro_break_status_emoji: str = ":coffee:"

    @field_validator(
        "slack_status_text", "slack_status_emoji",
        "pomodoro_work_status_text", "pomodoro_work_status_emoji",
        "pomodoro_break_status_text", "pomodoro_break_status_emoji",
        mode="before",
    )
    @classmethod
    def use_default_for_none(cls, v: str | None, info) -> str:
        if v is None:
            return _SLACK_STATUS_DEFAULTS[info.field_name]
        return v


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
