"""Triage system schemas for request/response validation."""

from datetime import datetime, timezone
from typing import Annotated

from pydantic import BaseModel, Field, PlainSerializer


def serialize_utc_datetime(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat().replace("+00:00", "Z")


UTCDatetime = Annotated[datetime | None, PlainSerializer(serialize_utc_datetime)]


# --- Triage User Settings ---


class TriageSettingsUpdate(BaseModel):
    """Request to update triage settings."""

    is_always_on: bool | None = None
    sensitivity: str | None = Field(None, pattern="^(low|medium|high)$")
    debug_mode: bool | None = None
    classification_retention_days: int | None = Field(None, ge=1, le=365)


class TriageSettingsResponse(BaseModel):
    """Response with triage settings."""

    model_config = {"from_attributes": True}

    is_always_on: bool = False
    sensitivity: str = "medium"
    debug_mode: bool = False
    slack_workspace_domain: str | None = None
    classification_retention_days: int = 30


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


class MonitoredChannelResponse(BaseModel):
    """Response with monitored channel info."""

    model_config = {"from_attributes": True}

    id: str
    slack_channel_id: str
    channel_name: str
    channel_type: str
    priority: str
    is_active: bool
    created_at: UTCDatetime = None


class MonitoredChannelList(BaseModel):
    """Response with list of monitored channels."""

    channels: list[MonitoredChannelResponse]


# --- Keyword Rules ---


class KeywordRuleCreate(BaseModel):
    """Request to add a keyword rule."""

    keyword_pattern: str = Field(..., min_length=1, max_length=255)
    match_type: str = Field("contains", pattern="^(exact|contains)$")
    urgency_override: str | None = Field(
        None, pattern="^(urgent|review_at_break)$"
    )


class KeywordRuleUpdate(BaseModel):
    """Request to update a keyword rule."""

    keyword_pattern: str | None = Field(None, min_length=1, max_length=255)
    match_type: str | None = Field(None, pattern="^(exact|contains)$")
    urgency_override: str | None = Field(
        None, pattern="^(urgent|review_at_break)$"
    )


class KeywordRuleResponse(BaseModel):
    """Response with keyword rule info."""

    model_config = {"from_attributes": True}

    id: str
    keyword_pattern: str
    match_type: str
    urgency_override: str | None = None


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
    urgency_level: str
    confidence: float
    classification_reason: str | None = None
    abstract: str | None = None
    classification_path: str
    escalated_by_sender: bool = False
    surfaced_at_break: bool = False
    keyword_matches: dict | None = None
    created_at: UTCDatetime = None


class ClassificationList(BaseModel):
    """Response with list of classifications."""

    items: list[ClassificationResponse]
    total: int = 0


# --- Digest ---


class DigestResponse(BaseModel):
    """Response with a structured digest for a focus session."""

    session_id: str | None = None
    urgent_count: int = 0
    review_count: int = 0
    digest_count: int = 0
    items: list[ClassificationResponse] = []


# --- Feedback ---


class TriageFeedbackCreate(BaseModel):
    """Request to submit feedback on a classification."""

    classification_id: str = Field(..., min_length=1)
    was_correct: bool
    correct_urgency: str | None = Field(
        None, pattern="^(urgent|review_at_break|digest)$"
    )


# --- Slack Channel Info ---


class SlackChannelInfo(BaseModel):
    """Available Slack channel from conversations.list."""

    id: str
    name: str
    is_private: bool = False
    num_members: int = 0
