"""Add bypass notification config to focus settings.

Revision ID: 008_add_bypass_notify_config
Revises: 007_add_dashboard_tables
Create Date: 2026-02-21
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "008_add_bypass_notify_config"
down_revision: str | None = "007_add_dashboard_tables"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add bypass_notification_config column to focus_settings."""
    op.add_column(
        "focus_settings",
        sa.Column("bypass_notification_config", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    """Remove bypass_notification_config column from focus_settings."""
    op.drop_column("focus_settings", "bypass_notification_config")
