"""Add triage system tables.

Revision ID: 022_add_triage_tables
Revises: 021_add_session_summary_fields
Create Date: 2026-03-21
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "022_add_triage_tables"
down_revision: str | None = "021_add_session_summary_fields"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create triage system tables."""

    # --- triage_user_settings ---
    op.create_table(
        "triage_user_settings",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column(
            "user_id",
            sa.dialects.postgresql.UUID(as_uuid=False),
            sa.ForeignKey("users.id"),
            nullable=False,
            unique=True,
        ),
        sa.Column("is_always_on", sa.Boolean(), default=False, nullable=False, server_default="false"),
        sa.Column("sensitivity", sa.String(10), default="medium", nullable=False, server_default="medium"),
        sa.Column("debug_mode", sa.Boolean(), default=False, nullable=False, server_default="false"),
        sa.Column("slack_workspace_domain", sa.String(255), nullable=True),
        sa.Column("classification_retention_days", sa.Integer(), default=30, nullable=False, server_default="30"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )

    # --- monitored_channels ---
    op.create_table(
        "monitored_channels",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column(
            "user_id",
            sa.dialects.postgresql.UUID(as_uuid=False),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column("slack_channel_id", sa.String(50), nullable=False),
        sa.Column("channel_name", sa.String(255), nullable=False),
        sa.Column("channel_type", sa.String(10), default="public", nullable=False, server_default="public"),
        sa.Column("priority", sa.String(10), default="medium", nullable=False, server_default="medium"),
        sa.Column("is_active", sa.Boolean(), default=True, nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )
    op.create_index(
        "ix_monitored_channels_user_id",
        "monitored_channels",
        ["user_id"],
    )
    op.create_index(
        "ix_monitored_channels_slack_channel_id",
        "monitored_channels",
        ["slack_channel_id"],
    )
    op.create_unique_constraint(
        "uq_monitored_channels_user_channel",
        "monitored_channels",
        ["user_id", "slack_channel_id"],
    )

    # --- channel_keyword_rules ---
    op.create_table(
        "channel_keyword_rules",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column(
            "monitored_channel_id",
            sa.dialects.postgresql.UUID(as_uuid=False),
            sa.ForeignKey("monitored_channels.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            sa.dialects.postgresql.UUID(as_uuid=False),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column("keyword_pattern", sa.String(255), nullable=False),
        sa.Column("match_type", sa.String(20), default="contains", nullable=False, server_default="contains"),
        sa.Column("urgency_override", sa.String(20), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )
    op.create_index(
        "ix_channel_keyword_rules_channel_id",
        "channel_keyword_rules",
        ["monitored_channel_id"],
    )

    # --- channel_source_exclusions ---
    op.create_table(
        "channel_source_exclusions",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column(
            "monitored_channel_id",
            sa.dialects.postgresql.UUID(as_uuid=False),
            sa.ForeignKey("monitored_channels.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            sa.dialects.postgresql.UUID(as_uuid=False),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column("slack_entity_id", sa.String(50), nullable=False),
        sa.Column("entity_type", sa.String(10), default="bot", nullable=False, server_default="bot"),
        sa.Column("action", sa.String(10), default="exclude", nullable=False, server_default="exclude"),
        sa.Column("display_name", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )
    op.create_index(
        "ix_channel_source_exclusions_channel_id",
        "channel_source_exclusions",
        ["monitored_channel_id"],
    )
    op.create_unique_constraint(
        "uq_channel_source_exclusion_entity",
        "channel_source_exclusions",
        ["monitored_channel_id", "slack_entity_id"],
    )

    # --- triage_classifications ---
    op.create_table(
        "triage_classifications",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column(
            "user_id",
            sa.dialects.postgresql.UUID(as_uuid=False),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column(
            "focus_session_id",
            sa.dialects.postgresql.UUID(as_uuid=False),
            sa.ForeignKey("focus_mode_state.id"),
            nullable=True,
        ),
        sa.Column("sender_slack_id", sa.String(50), nullable=False),
        sa.Column("channel_id", sa.String(50), nullable=False),
        sa.Column("message_ts", sa.String(50), nullable=False),
        sa.Column("thread_ts", sa.String(50), nullable=True),
        sa.Column("slack_permalink", sa.Text(), nullable=True),
        sa.Column("urgency_level", sa.String(20), nullable=False),
        sa.Column("confidence", sa.Float(), default=0.0, nullable=False, server_default="0.0"),
        sa.Column("classification_reason", sa.Text(), nullable=True),
        sa.Column("abstract", sa.Text(), nullable=True),
        sa.Column("classification_path", sa.String(10), nullable=False),
        sa.Column("escalated_by_sender", sa.Boolean(), default=False, nullable=False, server_default="false"),
        sa.Column("surfaced_at_break", sa.Boolean(), default=False, nullable=False, server_default="false"),
        sa.Column("keyword_matches", sa.dialects.postgresql.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )
    op.create_index(
        "ix_triage_classifications_user_id",
        "triage_classifications",
        ["user_id"],
    )
    op.create_index(
        "ix_triage_classifications_session",
        "triage_classifications",
        ["user_id", "focus_session_id"],
    )
    op.create_index(
        "ix_triage_classifications_urgency",
        "triage_classifications",
        ["user_id", "urgency_level"],
    )
    op.create_index(
        "ix_triage_classifications_created",
        "triage_classifications",
        ["user_id", "created_at"],
    )

    # --- sender_behavior_models ---
    op.create_table(
        "sender_behavior_models",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column(
            "user_id",
            sa.dialects.postgresql.UUID(as_uuid=False),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column("sender_slack_id", sa.String(50), nullable=False),
        sa.Column("avg_response_time_seconds", sa.Float(), nullable=True),
        sa.Column("response_pattern", sa.String(20), default="normal", nullable=False, server_default="normal"),
        sa.Column("interaction_frequency", sa.String(20), default="medium", nullable=False, server_default="medium"),
        sa.Column("total_interactions", sa.Integer(), default=0, nullable=False, server_default="0"),
        sa.Column("last_computed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )
    op.create_unique_constraint(
        "uq_sender_behavior_user_sender",
        "sender_behavior_models",
        ["user_id", "sender_slack_id"],
    )

    # --- triage_feedback ---
    op.create_table(
        "triage_feedback",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column(
            "classification_id",
            sa.dialects.postgresql.UUID(as_uuid=False),
            sa.ForeignKey("triage_classifications.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            sa.dialects.postgresql.UUID(as_uuid=False),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column("was_correct", sa.Boolean(), nullable=False),
        sa.Column("correct_urgency", sa.String(20), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )
    op.create_index(
        "ix_triage_feedback_classification_id",
        "triage_feedback",
        ["classification_id"],
        unique=True,
    )


def downgrade() -> None:
    """Drop triage system tables."""
    op.drop_table("triage_feedback")
    op.drop_table("sender_behavior_models")
    op.drop_table("triage_classifications")
    op.drop_table("channel_source_exclusions")
    op.drop_table("channel_keyword_rules")
    op.drop_table("monitored_channels")
    op.drop_table("triage_user_settings")
