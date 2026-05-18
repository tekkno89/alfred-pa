"""add active hours config

Revision ID: 053
Revises: 052
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "053"
down_revision = "052"
depends_on = None


def upgrade() -> None:
    op.create_table(
        "active_hours_config",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("day_of_week", sa.Integer(), nullable=False),
        sa.Column("start_time", sa.String(5), nullable=False),
        sa.Column("end_time", sa.String(5), nullable=False),
        sa.Column("is_enabled", sa.Boolean(), server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("user_id", "day_of_week", name="uq_active_hours_user_day"),
    )

    op.create_index("ix_active_hours_config_user_id", "active_hours_config", ["user_id"])

    op.add_column(
        "triage_user_settings",
        sa.Column(
            "active_hours_breakthrough",
            sa.String(20),
            server_default="allow_notify_now",
        ),
    )


def downgrade() -> None:
    op.drop_column("triage_user_settings", "active_hours_breakthrough")

    op.drop_index("ix_active_hours_config_user_id")
    op.drop_table("active_hours_config")
