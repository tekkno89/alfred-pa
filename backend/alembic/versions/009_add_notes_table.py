"""Add notes table.

Revision ID: 009_add_notes_table
Revises: 008_add_bypass_notify_config
Create Date: 2026-02-22
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "009_add_notes_table"
down_revision: str | None = "008_add_bypass_notify_config"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create notes table."""
    op.create_table(
        "notes",
        sa.Column("id", sa.UUID(as_uuid=False), primary_key=True),
        sa.Column(
            "user_id",
            sa.UUID(as_uuid=False),
            sa.ForeignKey("users.id", name="fk_notes_user_id_users"),
            nullable=False,
        ),
        sa.Column("title", sa.String(500), server_default="", nullable=False),
        sa.Column("body", sa.Text(), server_default="", nullable=False),
        sa.Column(
            "is_favorited", sa.Boolean(), server_default="false", nullable=False
        ),
        sa.Column(
            "is_archived", sa.Boolean(), server_default="false", nullable=False
        ),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_notes"),
    )
    op.create_index("ix_notes_user_id", "notes", ["user_id"])
    op.create_index("ix_notes_user_id_is_archived", "notes", ["user_id", "is_archived"])


def downgrade() -> None:
    """Drop notes table."""
    op.drop_index("ix_notes_user_id_is_archived", table_name="notes")
    op.drop_index("ix_notes_user_id", table_name="notes")
    op.drop_table("notes")
