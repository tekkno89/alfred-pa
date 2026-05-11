"""add sender action distributions

Revision ID: 041
Revises: 040
Create Date: 2026-05-11

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "041"
down_revision = "040"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "sender_action_distributions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column("sender_slack_id", sa.String(50), nullable=False),
        sa.Column("channel_id", sa.String(50), nullable=False),
        sa.Column("action_distribution", postgresql.JSONB(), nullable=False),
        sa.Column(
            "sample_count", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column("last_computed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_sender_action_dist_unique",
        "sender_action_distributions",
        ["user_id", "sender_slack_id", "channel_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_sender_action_dist_unique")
    op.drop_table("sender_action_distributions")
