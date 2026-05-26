"""rename priority_level to action in conversation_summaries

Revision ID: 054
Revises: 053
Create Date: 2026-05-26

"""

from alembic import op

revision = "054"
down_revision = "053"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "conversation_summaries",
        "priority_level",
        new_column_name="action",
    )


def downgrade() -> None:
    op.alter_column(
        "conversation_summaries",
        "action",
        new_column_name="priority_level",
    )
