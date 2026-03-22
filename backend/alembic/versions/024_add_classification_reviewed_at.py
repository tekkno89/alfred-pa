"""Add reviewed_at column to triage_classifications.

Revision ID: 024
Revises: 023
"""

from alembic import op
import sqlalchemy as sa

revision = "024_add_reviewed_at"
down_revision = "023_add_triage_display_names"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "triage_classifications",
        sa.Column("reviewed_at", sa.DateTime(), nullable=True),
    )
    op.create_index(
        "ix_triage_classifications_user_reviewed",
        "triage_classifications",
        ["user_id", "reviewed_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_triage_classifications_user_reviewed",
        table_name="triage_classifications",
    )
    op.drop_column("triage_classifications", "reviewed_at")
