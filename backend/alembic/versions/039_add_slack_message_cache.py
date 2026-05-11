"""add slack_message_cache table

Revision ID: 039
Revises: 038
Create Date: 2026-05-11

"""

import sqlalchemy as sa
from alembic import op

revision = "039"
down_revision = "038"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "slack_message_cache",
        sa.Column("workspace_id", sa.String(50), nullable=False),
        sa.Column("channel_id", sa.String(50), nullable=False),
        sa.Column("message_ts", sa.String(50), nullable=False),
        sa.Column("parent_thread_ts", sa.String(50), nullable=True),
        sa.Column("sender_slack_id", sa.String(50), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("is_bot", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("cached_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.PrimaryKeyConstraint("workspace_id", "channel_id", "message_ts"),
    )
    op.create_index(
        "ix_slack_message_cache_thread",
        "slack_message_cache",
        ["workspace_id", "channel_id", "parent_thread_ts"],
    )
    op.create_index(
        "ix_slack_message_cache_cached_at",
        "slack_message_cache",
        ["cached_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_slack_message_cache_cached_at", table_name="slack_message_cache")
    op.drop_index("ix_slack_message_cache_thread", table_name="slack_message_cache")
    op.drop_table("slack_message_cache")
