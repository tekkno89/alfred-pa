"""Triage system models for Slack message classification."""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import ARRAY, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.db.models.user import User


class TriageUserSettings(Base, UUIDMixin, TimestampMixin):
    """Per-user triage configuration."""

    __tablename__ = "triage_user_settings"

    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id"), nullable=False, unique=True
    )
    is_always_on: Mapped[bool] = mapped_column(Boolean, default=False)
    always_on_min_priority: Mapped[str] = mapped_column(String(2), default="p3", server_default="p3")
    # low = fewer urgent, high = more urgent
    sensitivity: Mapped[str] = mapped_column(String(10), default="medium")
    debug_mode: Mapped[bool] = mapped_column(Boolean, default=False)
    slack_workspace_domain: Mapped[str | None] = mapped_column(
        String(255), nullable=True
    )
    classification_retention_days: Mapped[int] = mapped_column(Integer, default=30)
    custom_classification_rules: Mapped[str | None] = mapped_column(
        Text, nullable=True
    )
    p0_definition: Mapped[str | None] = mapped_column(Text, nullable=True)
    p1_definition: Mapped[str | None] = mapped_column(Text, nullable=True)
    p2_definition: Mapped[str | None] = mapped_column(Text, nullable=True)
    p3_definition: Mapped[str | None] = mapped_column(Text, nullable=True)
    digest_instructions: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Summary cadence configuration
    p1_digest_interval_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    p1_digest_active_hours_start: Mapped[str | None] = mapped_column(String(10), nullable=True)
    p1_digest_active_hours_end: Mapped[str | None] = mapped_column(String(10), nullable=True)
    p1_digest_times: Mapped[list[str] | None] = mapped_column(ARRAY(String), nullable=True)
    p1_digest_outside_hours_behavior: Mapped[str | None] = mapped_column(String(20), nullable=True)

    p2_digest_interval_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    p2_digest_active_hours_start: Mapped[str | None] = mapped_column(String(10), nullable=True)
    p2_digest_active_hours_end: Mapped[str | None] = mapped_column(String(10), nullable=True)
    p2_digest_times: Mapped[list[str] | None] = mapped_column(ARRAY(String), nullable=True)
    p2_digest_outside_hours_behavior: Mapped[str | None] = mapped_column(String(20), nullable=True)

    p3_digest_time: Mapped[str | None] = mapped_column(String(10), nullable=True)

    # Alert deduplication
    alert_dedup_window_minutes: Mapped[int] = mapped_column(Integer, default=30, server_default="30")

    # Alert enabled toggles per priority
    p0_alerts_enabled: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    p1_alerts_enabled: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    p2_alerts_enabled: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    p3_alerts_enabled: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")

    # Relationships
    user: Mapped["User"] = relationship("User")

    def __repr__(self) -> str:
        return f"<TriageUserSettings(user_id={self.user_id}, sensitivity={self.sensitivity})>"


class MonitoredChannel(Base, UUIDMixin, TimestampMixin):
    """A Slack channel monitored for triage."""

    __tablename__ = "monitored_channels"

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    slack_channel_id: Mapped[str] = mapped_column(String(50), nullable=False)
    channel_name: Mapped[str] = mapped_column(String(255), nullable=False)
    # public | private
    channel_type: Mapped[str] = mapped_column(String(10), default="public")
    # low | medium | high | critical
    priority: Mapped[str] = mapped_column(String(10), default="medium")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    # Relationships
    user: Mapped["User"] = relationship("User")
    keyword_rules: Mapped[list["ChannelKeywordRule"]] = relationship(
        "ChannelKeywordRule", back_populates="channel", cascade="all, delete-orphan"
    )
    source_exclusions: Mapped[list["ChannelSourceExclusion"]] = relationship(
        "ChannelSourceExclusion",
        back_populates="channel",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<MonitoredChannel(user_id={self.user_id}, channel={self.channel_name})>"


class ChannelKeywordRule(Base, UUIDMixin, TimestampMixin):
    """Keyword-based urgency override for a monitored channel."""

    __tablename__ = "channel_keyword_rules"

    monitored_channel_id: Mapped[str] = mapped_column(
        ForeignKey("monitored_channels.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    keyword_pattern: Mapped[str] = mapped_column(String(255), nullable=False)
    # exact | contains (semantic deferred to v2)
    match_type: Mapped[str] = mapped_column(String(20), default="contains")
    # p0 | p1 | p2 | p3 | review | null (null = no override, use LLM)
    priority_override: Mapped[str | None] = mapped_column(String(20), nullable=True)

    # Relationships
    channel: Mapped["MonitoredChannel"] = relationship(
        "MonitoredChannel", back_populates="keyword_rules"
    )

    def __repr__(self) -> str:
        return f"<ChannelKeywordRule(channel={self.monitored_channel_id}, pattern={self.keyword_pattern})>"


class ChannelSourceExclusion(Base, UUIDMixin, TimestampMixin):
    """Per-channel bot/user exclusion or inclusion override."""

    __tablename__ = "channel_source_exclusions"

    monitored_channel_id: Mapped[str] = mapped_column(
        ForeignKey("monitored_channels.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    slack_entity_id: Mapped[str] = mapped_column(String(50), nullable=False)
    # bot | user
    entity_type: Mapped[str] = mapped_column(String(10), default="bot")
    # exclude | include
    action: Mapped[str] = mapped_column(String(10), default="exclude")
    display_name: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Relationships
    channel: Mapped["MonitoredChannel"] = relationship(
        "MonitoredChannel", back_populates="source_exclusions"
    )

    def __repr__(self) -> str:
        return f"<ChannelSourceExclusion(entity={self.slack_entity_id}, action={self.action})>"


class TriageClassification(Base, UUIDMixin, TimestampMixin):
    """A classified Slack message (no raw text stored)."""

    __tablename__ = "triage_classifications"

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    focus_session_id: Mapped[str | None] = mapped_column(
        ForeignKey("focus_mode_state.id"), nullable=True
    )
    sender_slack_id: Mapped[str] = mapped_column(String(50), nullable=False)
    sender_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    channel_id: Mapped[str] = mapped_column(String(50), nullable=False)
    channel_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    message_ts: Mapped[str] = mapped_column(String(50), nullable=False)
    thread_ts: Mapped[str | None] = mapped_column(String(50), nullable=True)
    slack_permalink: Mapped[str | None] = mapped_column(Text, nullable=True)
    focus_started_at: Mapped[datetime | None] = mapped_column(nullable=True)
    # p0 | p1 | p2 | p3 | review | digest_summary
    priority_level: Mapped[str] = mapped_column(String(20), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    classification_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    abstract: Mapped[str | None] = mapped_column(Text, nullable=True)
    # dm | channel
    classification_path: Mapped[str] = mapped_column(String(10), nullable=False)
    escalated_by_sender: Mapped[bool] = mapped_column(Boolean, default=False)
    surfaced_at_break: Mapped[bool] = mapped_column(Boolean, default=False)
    keyword_matches: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(nullable=True)
    # Digest consolidation
    digest_summary_id: Mapped[str | None] = mapped_column(
        ForeignKey("triage_classifications.id", ondelete="SET NULL"), nullable=True
    )
    child_count: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Alert tracking
    last_alerted_at: Mapped[datetime | None] = mapped_column(nullable=True)
    alert_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")

    # Relationships
    user: Mapped["User"] = relationship("User")
    feedback: Mapped["TriageFeedback | None"] = relationship(
        "TriageFeedback", back_populates="classification", uselist=False
    )

    def __repr__(self) -> str:
        return f"<TriageClassification(user_id={self.user_id}, priority={self.priority_level})>"


class SenderBehaviorModel(Base, UUIDMixin, TimestampMixin):
    """Behavioral model for a sender (bootstrapped with defaults in v1)."""

    __tablename__ = "sender_behavior_models"

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    sender_slack_id: Mapped[str] = mapped_column(String(50), nullable=False)
    avg_response_time_seconds: Mapped[float | None] = mapped_column(
        Float, nullable=True
    )
    # immediate | quick | normal | slow
    response_pattern: Mapped[str] = mapped_column(String(20), default="normal")
    # high | medium | low | rare
    interaction_frequency: Mapped[str] = mapped_column(String(20), default="medium")
    total_interactions: Mapped[int] = mapped_column(Integer, default=0)
    last_computed_at: Mapped[datetime | None] = mapped_column(nullable=True)

    # Relationships
    user: Mapped["User"] = relationship("User")

    # UNIQUE constraint on (user_id, sender_slack_id)
    __table_args__ = (
        {"comment": "UNIQUE(user_id, sender_slack_id) enforced via migration index"},
    )

    def __repr__(self) -> str:
        return f"<SenderBehaviorModel(user_id={self.user_id}, sender={self.sender_slack_id})>"


class SlackChannelCache(Base, UUIDMixin, TimestampMixin):
    """Cached Slack channel list (global, not per-user)."""

    __tablename__ = "slack_channel_cache"

    slack_channel_id: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    is_private: Mapped[bool] = mapped_column(Boolean, default=False)
    num_members: Mapped[int] = mapped_column(Integer, default=0)

    def __repr__(self) -> str:
        return f"<SlackChannelCache(name={self.name}, id={self.slack_channel_id})>"


class TriageFeedback(Base, UUIDMixin, TimestampMixin):
    """User feedback on a classification decision."""

    __tablename__ = "triage_feedback"

    classification_id: Mapped[str] = mapped_column(
        ForeignKey("triage_classifications.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    was_correct: Mapped[bool] = mapped_column(Boolean, nullable=False)
    # p0 | p1 | p2 | p3 | review (what it should have been)
    correct_priority: Mapped[str | None] = mapped_column(String(20), nullable=True)
    feedback_text: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships
    classification: Mapped["TriageClassification"] = relationship(
        "TriageClassification", back_populates="feedback"
    )

    def __repr__(self) -> str:
        return f"<TriageFeedback(classification={self.classification_id}, correct={self.was_correct})>"
