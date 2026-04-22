"""Triage system schemas for request/response validation."""

from datetime import UTC, datetime
from typing import Annotated

from pydantic import BaseModel, Field, PlainSerializer


def serialize_utc_datetime(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.isoformat().replace("+00:00", "Z")


UTCDatetime = Annotated[datetime | None, PlainSerializer(serialize_utc_datetime)]


# --- Triage User Settings ---


class TriageSettingsUpdate(BaseModel):
    """Request to update triage settings."""

    is_always_on: bool | None = None
    sensitivity: str | None = Field(None, pattern="^(low|medium|high)$")
    debug_mode: bool | None = None
    classification_retention_days: int | None = Field(None, ge=1, le=365)
    custom_classification_rules: str | None = Field(None, max_length=2000)
    p0_definition: str | None = Field(None, max_length=2000)
    p1_definition: str | None = Field(None, max_length=2000)
    p2_definition: str | None = Field(None, max_length=2000)
    p3_definition: str | None = Field(None, max_length=2000)
    digest_instructions: str | None = Field(None, max_length=2000)

    # Summary cadence configuration
    p1_digest_interval_minutes: int | None = Field(None, ge=5, le=180)
    p1_digest_active_hours_start: str | None = Field(None, max_length=10)
    p1_digest_active_hours_end: str | None = Field(None, max_length=10)
    p1_digest_times: list[str] | None = None
    p1_digest_outside_hours_behavior: str | None = Field(
        None, pattern="^(summary_next_window|skip)$"
    )

    p2_digest_interval_minutes: int | None = Field(None, ge=5, le=360)
    p2_digest_active_hours_start: str | None = Field(None, max_length=10)
    p2_digest_active_hours_end: str | None = Field(None, max_length=10)
    p2_digest_times: list[str] | None = None
    p2_digest_outside_hours_behavior: str | None = Field(
        None, pattern="^(summary_next_window|skip)$"
    )

    p3_digest_time: str | None = Field(None, max_length=10)
    alert_dedup_window_minutes: int | None = Field(None, ge=1, le=120)
    p0_alerts_enabled: bool | None = None
    p1_alerts_enabled: bool | None = None
    p2_alerts_enabled: bool | None = None
    p3_alerts_enabled: bool | None = None


class TriageSettingsResponse(BaseModel):
    """Response with triage settings."""

    model_config = {"from_attributes": True}

    is_always_on: bool = False
    sensitivity: str = "medium"
    debug_mode: bool = False
    slack_workspace_domain: str | None = None
    classification_retention_days: int = 30
    custom_classification_rules: str | None = None
    p0_definition: str | None = None
    p1_definition: str | None = None
    p2_definition: str | None = None
    p3_definition: str | None = None
    digest_instructions: str | None = None

    # Summary cadence configuration
    p1_digest_interval_minutes: int | None = None
    p1_digest_active_hours_start: str | None = None
    p1_digest_active_hours_end: str | None = None
    p1_digest_times: list[str] | None = None
    p1_digest_outside_hours_behavior: str | None = None

    p2_digest_interval_minutes: int | None = None
    p2_digest_active_hours_start: str | None = None
    p2_digest_active_hours_end: str | None = None
    p2_digest_times: list[str] | None = None
    p2_digest_outside_hours_behavior: str | None = None

    p3_digest_time: str | None = None
    alert_dedup_window_minutes: int = 30
    p0_alerts_enabled: bool = True
    p1_alerts_enabled: bool = True
    p2_alerts_enabled: bool = True
    p3_alerts_enabled: bool = True


# --- Monitored Channels ---


class MonitoredChannelCreate(BaseModel):
    """Request to add a monitored channel."""

    slack_channel_id: str = Field(..., min_length=1)
    channel_name: str = Field(..., min_length=1)
    channel_type: str = Field("public", pattern="^(public|private)$")
    priority: str = Field("medium", pattern="^(low|medium|high|critical)$")


class MonitoredChannelUpdate(BaseModel):
    """Request to update a monitored channel."""

    channel_name: str | None = None
    priority: str | None = Field(None, pattern="^(low|medium|high|critical)$")
    is_active: bool | None = None
    is_hidden: bool | None = None
    triage_instructions: str | None = Field(None, max_length=2000)


class MonitoredChannelResponse(BaseModel):
    """Response with monitored channel info."""

    model_config = {"from_attributes": True}

    id: str
    slack_channel_id: str
    channel_name: str
    channel_type: str
    priority: str
    is_active: bool
    is_hidden: bool = False
    triage_instructions: str | None = None
    created_at: UTCDatetime = None


class MonitoredChannelList(BaseModel):
    """Response with list of monitored channels."""

    channels: list[MonitoredChannelResponse]


# --- Source Exclusions ---


class SourceExclusionCreate(BaseModel):
    """Request to add a source exclusion."""

    slack_entity_id: str = Field(..., min_length=1)
    entity_type: str = Field("bot", pattern="^(bot|user)$")
    action: str = Field("exclude", pattern="^(exclude|include)$")
    display_name: str | None = None


class SourceExclusionResponse(BaseModel):
    """Response with source exclusion info."""

    model_config = {"from_attributes": True}

    id: str
    slack_entity_id: str
    entity_type: str
    action: str
    display_name: str | None = None


# --- Classifications ---


class ClassificationResponse(BaseModel):
    """Response with a single classification."""

    model_config = {"from_attributes": True}

    id: str
    sender_slack_id: str
    sender_name: str | None = None
    channel_id: str
    channel_name: str | None = None
    message_ts: str
    thread_ts: str | None = None
    slack_permalink: str | None = None
    priority_level: str
    confidence: float
    classification_reason: str | None = None
    abstract: str | None = None
    classification_path: str
    escalated_by_sender: bool = False
    surfaced_at_break: bool = False
    keyword_matches: dict | None = None
    reviewed_at: UTCDatetime = None
    focus_session_id: str | None = None
    focus_started_at: UTCDatetime = None
    digest_summary_id: str | None = None
    child_count: int | None = None
    digest_type: str | None = None
    created_at: UTCDatetime = None
    user_reacted_at: UTCDatetime = None
    user_responded_at: UTCDatetime = None


class MarkReviewedRequest(BaseModel):
    """Request to mark classifications as reviewed or unreviewed."""

    classification_ids: list[str] = Field(..., min_length=1)
    reviewed: bool = True


class MarkAllReviewedRequest(BaseModel):
    """Request to mark all classifications matching a filter as reviewed."""

    filter: str = Field(
        "needs_attention", pattern="^(needs_attention|focus|scheduled|review)$"
    )


class ClassificationList(BaseModel):
    """Response with list of classifications."""

    items: list[ClassificationResponse]
    total: int = 0


# --- Digest ---


class DigestResponse(BaseModel):
    """Response with a structured digest for a focus session."""

    session_id: str | None = None
    p0_count: int = 0
    p1_count: int = 0
    p2_count: int = 0
    p3_count: int = 0
    review_count: int = 0
    items: list[ClassificationResponse] = []


# --- Feedback ---


class TriageFeedbackCreate(BaseModel):
    """Request to submit feedback on a classification."""

    classification_id: str = Field(..., min_length=1)
    was_correct: bool
    correct_priority: str | None = Field(None, pattern="^(p0|p1|p2|p3|review)$")
    feedback_text: str | None = Field(None, max_length=2000)


# --- Slack Channel Info ---


class SlackChannelInfo(BaseModel):
    """Available Slack channel from conversations.list."""

    id: str
    name: str
    is_private: bool = False
    num_members: int = 0


class ChannelMemberInfo(BaseModel):
    """Member of a Slack channel (user, bot, or app)."""

    slack_user_id: str
    display_name: str
    is_bot: bool = False
    is_app: bool = False


# --- AI Wizard ---


class GenerateDefinitionsRequest(BaseModel):
    """Request for AI-generated priority definitions."""

    role: str = Field(..., min_length=1, max_length=500)
    critical_messages: str = Field(..., min_length=1, max_length=1000)
    can_wait: str = Field(..., min_length=1, max_length=1000)
    priority_senders: str = Field("", max_length=1000)


class GenerateDefinitionsResponse(BaseModel):
    """Response with AI-generated priority definitions."""

    p0_definition: str
    p1_definition: str
    p2_definition: str
    p3_definition: str


# --- Calibration ---


class CalibrationMessage(BaseModel):
    """A Slack message sampled for priority calibration."""

    message_id: str  # Unique ID: "{channel_id}:{message_ts}"
    message_text: str
    sender_name: str
    sender_slack_id: str
    channel_name: str
    channel_type: str = Field(..., pattern="^(public|private|dm)$")
    message_ts: str
    channel_id: str
    permalink: str | None = None


class CalibrationRating(BaseModel):
    """User's priority rating for a calibration message."""

    message_id: str  # Unique ID to track which messages were rated
    message_text: str
    sender_name: str
    channel_name: str
    priority: str = Field(..., pattern="^(p0|p1|p2|p3)?$")
    explanation: str | None = Field(None, max_length=500)


class CalibrateGenerateRequest(BaseModel):
    """Request to generate definitions from calibration data."""

    role: str = Field(..., min_length=1, max_length=500)
    critical_messages: str = Field(..., min_length=1, max_length=1000)
    can_wait: str = Field(..., min_length=1, max_length=1000)
    priority_senders: str = Field("", max_length=1000)
    ratings: list[CalibrationRating] = Field(default_factory=list)


class SampleMessagesRequest(BaseModel):
    """Request to sample messages for calibration."""

    exclude_message_ids: list[str] = Field(default_factory=list, max_length=100)


class FetchMessageByLinkRequest(BaseModel):
    """Request to fetch a specific Slack message by permalink."""

    permalink: str = Field(..., min_length=10, max_length=500)
