"""Add custom_classification_rules to triage_user_settings.

Revision ID: 025
Revises: 024
"""

from alembic import op
import sqlalchemy as sa

revision = "025_custom_class_rules"
down_revision = "024_add_reviewed_at"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "triage_user_settings",
        sa.Column("custom_classification_rules", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("triage_user_settings", "custom_classification_rules")
