"""Add always_on_min_priority to triage_user_settings.

Revision ID: 030_always_on_min_prio
Revises: 029_triage_prio
"""

from alembic import op
import sqlalchemy as sa

revision = "030_always_on_min_prio"
down_revision = "029_triage_prio"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "triage_user_settings",
        sa.Column("always_on_min_priority", sa.String(2), server_default="p3", nullable=False),
    )


def downgrade() -> None:
    op.drop_column("triage_user_settings", "always_on_min_priority")
