"""Add sender_name and channel_name to triage_classifications.

Revision ID: 023
Revises: 022
"""

from alembic import op
import sqlalchemy as sa

revision = "023_add_triage_display_names"
down_revision = "022_add_triage_tables"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "triage_classifications",
        sa.Column("sender_name", sa.String(200), nullable=True),
    )
    op.add_column(
        "triage_classifications",
        sa.Column("channel_name", sa.String(200), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("triage_classifications", "channel_name")
    op.drop_column("triage_classifications", "sender_name")
