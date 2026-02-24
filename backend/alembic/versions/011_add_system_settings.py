"""Add system_settings table.

Revision ID: 011_add_system_settings
Revises: 010_add_notes_tags
Create Date: 2026-02-23
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "011_add_system_settings"
down_revision: str | None = "010_add_notes_tags"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create system_settings table and seed defaults."""
    op.create_table(
        "system_settings",
        sa.Column("key", sa.String(100), primary_key=True, nullable=False),
        sa.Column("value", sa.Text, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime,
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime,
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    # Seed the auto-reply toggle, enabled by default
    op.execute(
        "INSERT INTO system_settings (key, value) "
        "VALUES ('focus_auto_reply_enabled', 'true')"
    )


def downgrade() -> None:
    """Drop system_settings table."""
    op.drop_table("system_settings")
