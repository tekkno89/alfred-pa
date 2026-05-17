"""Triage system models for Slack message classification."""

from datetime import datetime
from typing import TYPE_CHECKING

from pgvector.sqlalchemy import Vector
from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import ARRAY, JSON, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.db.models.conversation_summary import ConversationSummary
    from app.db.models.user import User


class TriageUserSettings(Base, UUIDMixin, TimestampMixin):
    """Per-user triage configuration."""

    __tablename__ = "triage_user_settings"

    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id"), nullable=False, unique=True
    )
    is_always_on: Mapped[bool] = mapped_column(Boolean, default=False)
    # low = fewer urgent, high = more urgent
    sensitivity: Mapped[str] = mapped_column(String(10), default="medium")
    debug_mode: Mapped[bool] = mapped_column(Boolean, default=False)
    slack_workspace_domain: Mapped[str | None] = mapped_column(
        String(255), nullable=True
    )
    classification_retention_days: Mapped[int] = mapped_column(Integer, default=30)
    custom_classification_rules: Mapped[str | None] = mapped_column(Text, nullable=True)
    p0_definition: Mapped[str | None] = mapped_column(Text, nullable=True)
    p1_definition: Mapped[str | None] = mapped_column(Text, nullable=True)
    p2_definition: Mapped[str | None] = mapped_column(Text, nullable=True)
    p3_definition: Mapped[str | None] = mapped_column(Text, nullable=True)
    digest_instructions: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Summary cadence configuration
    p1_digest_interval_minutes: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )
    p1_digest_active_hours_start: Mapped[str | None] = mapped_column(
        String(10), nullable=True
    )
    p1_digest_active_hours_end: Mapped[str | None] = mapped_column(
        String(10), nullable=True
    )
    p1_digest_times: Mapped[list[str] | None] = mapped_column(
        ARRAY(String), nullable=True
    )
    p1_digest_outside_hours_behavior: Mapped[str | None] = mapped_column(
        String(20), nullable=True
    )

    p2_digest_interval_minutes: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )
    p2_digest_active_hours_start: Mapped[str | None] = mapped_column(
        String(10), nullable=True
    )
    p2_digest_active_hours_end: Mapped[str | None] = mapped_column(
        String(10), nullable=True
    )
    p2_digest_times: Mapped[list[str] | None] = mapped_column(
        ARRAY(String), nullable=True
    )
    p2_digest_outside_hours_behavior: Mapped[str | None] = mapped_column(
        String(20), nullable=True
    )

    p3_digest_time: Mapped[str | None] = mapped_column(String(10), nullable=True)

    # Alert deduplication
    alert_dedup_window_minutes: Mapped[int] = mapped_column(
        Integer, default=30, server_default="30"
    )

    # Alert enabled toggles per priority
    p0_alerts_enabled: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="true"
    )
    p1_alerts_enabled: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="true"
    )
    p2_alerts_enabled: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="true"
    )
    p3_alerts_enabled: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="true"
    )

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
    is_hidden: Mapped[bool] = mapped_column(Boolean, default=False)
    sensitive: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false"
    )
    triage_instructions: Mapped[str | None] = mapped_column(Text, nullable=True)
    summary_behavior: Mapped[str] = mapped_column(
        String(20), default="default", server_default="default"
    )

    # Relationships
    user: Mapped["User"] = relationship("User")
    source_exclusions: Mapped[list["ChannelSourceExclusion"]] = relationship(
        "ChannelSourceExclusion",
        back_populates="channel",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return (
            f"<MonitoredChannel(user_id={self.user_id}, channel={self.channel_name})>"
        )


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

    action: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    review: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    is_consolidated: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")

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

    conversation_summary_id: Mapped[str | None] = mapped_column(
        ForeignKey("conversation_summaries.id", ondelete="SET NULL"), nullable=True
    )

    # Alert tracking
    last_alerted_at: Mapped[datetime | None] = mapped_column(nullable=True)
    alert_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")

    # Digest queue tracking
    queued_for_digest: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="true"
    )

    # Digest type: "focus" for focus session summaries, "scheduled" for scheduled digests
    digest_type: Mapped[str | None] = mapped_column(String(20), nullable=True)

    # Processing outcome for digest grouping
    # Values: summarized, filtered_nonsubstantive, absorbed_in_thread, absorbed_in_cluster, skipped_thin_update
    processed_reason: Mapped[str | None] = mapped_column(String(30), nullable=True)

    # Relationships
    user: Mapped["User"] = relationship("User")
    feedback: Mapped["TriageFeedback | None"] = relationship(
        "TriageFeedback", back_populates="classification", uselist=False
    )
    conversation_summary: Mapped["ConversationSummary | None"] = relationship(
        "ConversationSummary",
        foreign_keys=[conversation_summary_id],
        back_populates="messages",
    )

    def __repr__(self) -> str:
        return f"<TriageClassification(user_id={self.user_id}, action={self.action})>"


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

    slack_channel_id: Mapped[str] = mapped_column(
        String(50), unique=True, nullable=False
    )
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
    correct_action: Mapped[str | None] = mapped_column(String(20), nullable=True)
    feedback_text: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships
    classification: Mapped["TriageClassification"] = relationship(
        "TriageClassification", back_populates="feedback"
    )
    embedding: Mapped["FeedbackEmbedding | None"] = relationship(
        "FeedbackEmbedding", back_populates="feedback", uselist=False
    )

    def __repr__(self) -> str:
        return f"<TriageFeedback(classification={self.classification_id}, correct={self.was_correct})>"


class FeedbackEmbedding(Base, UUIDMixin, TimestampMixin):
    """Embedding of a corrected message for few-shot retrieval.

    Persists beyond R-Cache TTL since it's derived data (no raw text).
    Used by R3b to retrieve semantically similar past corrections.
    """

    __tablename__ = "feedback_embeddings"

    triage_feedback_id: Mapped[str] = mapped_column(
        ForeignKey("triage_feedback.id", ondelete="CASCADE"), nullable=False
    )
    embedding_vector: Mapped[list[float]] = mapped_column(
        Vector(768), nullable=False
    )
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    feedback: Mapped["TriageFeedback"] = relationship(
        "TriageFeedback", back_populates="embedding"
    )

    def __repr__(self) -> str:
        return f"<FeedbackEmbedding(feedback={self.triage_feedback_id})>"


class SenderActionDistribution(Base, UUIDMixin, TimestampMixin):
    """Per-(sender, channel) action distribution derived from corrections.

    Tracks the historical distribution of corrected actions for a sender
    in a specific channel, with 30-day half-life decay.
    Separate from SenderBehaviorModel which tracks response timing.
    """

    __tablename__ = "sender_action_distributions"

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    sender_slack_id: Mapped[str] = mapped_column(String(50), nullable=False)
    channel_id: Mapped[str] = mapped_column(String(50), nullable=False)
    action_distribution: Mapped[dict] = mapped_column(JSONB, nullable=False)
    sample_count: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0"
    )
    last_computed_at: Mapped[datetime | None] = mapped_column(nullable=True)

    user: Mapped["User"] = relationship("User")

    __table_args__ = (
        {"comment": "UNIQUE(user_id, sender_slack_id, channel_id) enforced via migration index"},
    )

    def __repr__(self) -> str:
        return f"<SenderActionDistribution(sender={self.sender_slack_id}, channel={self.channel_id})>"


class TopicAffinity(Base, UUIDMixin, TimestampMixin):
    """Per-user topic keyword with weight and source tracking.

    Derived data from message classification/correction.
    No raw text stored - only extracted keywords.

    Source categories for audit:
    - 'public': learned from public non-sensitive channels
    - 'sensitive': learned from sensitive-flagged public channels
    - 'dm': learned from DMs
    """

    __tablename__ = "topic_affinities"

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    keyword: Mapped[str] = mapped_column(String(100), nullable=False)
    weight: Mapped[float] = mapped_column(Float, nullable=False)
    source_category: Mapped[str] = mapped_column(String(50), nullable=False)
    last_updated: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    user: Mapped["User"] = relationship("User")

    __table_args__ = (
        {"comment": "UNIQUE(user_id, keyword) enforced via migration index"},
    )

    def __repr__(self) -> str:
        return f"<TopicAffinity(user={self.user_id}, keyword={self.keyword}, weight={self.weight})>"


class SuppressedDelivery(Base, UUIDMixin, TimestampMixin):
    """Record of a delivery suppressed by engagement check.

    Used for counterfactual review: "would you have wanted to know sooner?"
    Retained for 90 days.

    Canonical cap: 10 suppressed items per user per day.
    """

    __tablename__ = "suppressed_deliveries"

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    message_id: Mapped[str] = mapped_column(String(50), nullable=False)
    original_action: Mapped[str] = mapped_column(String(20), nullable=False)
    suppression_reason: Mapped[str] = mapped_column(String(50), nullable=False)
    outcome_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    user_review_response: Mapped[str | None] = mapped_column(String(20), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    user: Mapped["User"] = relationship("User")

    def __repr__(self) -> str:
        return f"<SuppressedDelivery(user={self.user_id}, action={self.original_action})>"
