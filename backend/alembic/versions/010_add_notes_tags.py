"""Add tags column to notes table.

Revision ID: 010_add_notes_tags
Revises: 009_add_notes_table
Create Date: 2026-02-22
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ARRAY

# revision identifiers, used by Alembic.
revision: str = "010_add_notes_tags"
down_revision: str | None = "009_add_notes_table"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add tags column to notes table."""
    op.add_column(
        "notes",
        sa.Column(
            "tags",
            ARRAY(sa.String(100)),
            server_default="{}",
            nullable=False,
        ),
    )
    op.create_index(
        "ix_notes_tags",
        "notes",
        ["tags"],
        postgresql_using="gin",
    )


def downgrade() -> None:
    """Remove tags column from notes table."""
    op.drop_index("ix_notes_tags", table_name="notes")
    op.drop_column("notes", "tags")
