"""Add focus mode tables.

Revision ID: 004_add_focus_mode_tables
Revises: 003_add_slack_user_id
Create Date: 2026-02-08
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "004_add_focus_mode_tables"
down_revision: str | None = "003_add_slack_user_id"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create focus mode tables."""
    # Focus mode state table
    op.create_table(
        "focus_mode_state",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("mode", sa.String(20), nullable=False, server_default="simple"),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("ends_at", sa.DateTime(), nullable=True),
        sa.Column("custom_message", sa.Text(), nullable=True),
        sa.Column("previous_slack_status", sa.JSON(), nullable=True),
        sa.Column("pomodoro_phase", sa.String(20), nullable=True),
        sa.Column("pomodoro_session_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_focus_mode_state_user_id_users"),
        sa.PrimaryKeyConstraint("id", name="pk_focus_mode_state"),
    )
    op.create_index("ix_focus_mode_state_user_id", "focus_mode_state", ["user_id"])
    op.create_index("ix_focus_mode_state_is_active", "focus_mode_state", ["is_active"])

    # Focus settings table
    op.create_table(
        "focus_settings",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("default_message", sa.Text(), nullable=True),
        sa.Column("pomodoro_work_minutes", sa.Integer(), nullable=False, server_default="25"),
        sa.Column("pomodoro_break_minutes", sa.Integer(), nullable=False, server_default="5"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_focus_settings_user_id_users"),
        sa.PrimaryKeyConstraint("id", name="pk_focus_settings"),
        sa.UniqueConstraint("user_id", name="uq_focus_settings_user_id"),
    )

    # Focus VIP list table
    op.create_table(
        "focus_vip_list",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("slack_user_id", sa.String(50), nullable=False),
        sa.Column("display_name", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_focus_vip_list_user_id_users"),
        sa.PrimaryKeyConstraint("id", name="pk_focus_vip_list"),
        sa.UniqueConstraint("user_id", "slack_user_id", name="uq_focus_vip_list_user_slack"),
    )
    op.create_index("ix_focus_vip_list_user_id", "focus_vip_list", ["user_id"])

    # Webhook subscriptions table
    op.create_table(
        "webhook_subscriptions",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("url", sa.String(2048), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("event_types", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_webhook_subscriptions_user_id_users"),
        sa.PrimaryKeyConstraint("id", name="pk_webhook_subscriptions"),
    )
    op.create_index("ix_webhook_subscriptions_user_id", "webhook_subscriptions", ["user_id"])

    # User OAuth tokens table
    op.create_table(
        "user_oauth_tokens",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("provider", sa.String(50), nullable=False),
        sa.Column("access_token", sa.Text(), nullable=False),
        sa.Column("refresh_token", sa.Text(), nullable=True),
        sa.Column("scope", sa.Text(), nullable=True),
        sa.Column("expires_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_user_oauth_tokens_user_id_users"),
        sa.PrimaryKeyConstraint("id", name="pk_user_oauth_tokens"),
        sa.UniqueConstraint("user_id", "provider", name="uq_user_oauth_tokens_user_provider"),
    )
    op.create_index("ix_user_oauth_tokens_user_id", "user_oauth_tokens", ["user_id"])


def downgrade() -> None:
    """Drop focus mode tables."""
    op.drop_table("user_oauth_tokens")
    op.drop_table("webhook_subscriptions")
    op.drop_table("focus_vip_list")
    op.drop_table("focus_settings")
    op.drop_table("focus_mode_state")
