"""Add slack status customization columns to focus settings.

Revision ID: 012_add_slack_status_custom
Revises: 011_add_system_settings
Create Date: 2026-02-28
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "012_add_slack_status_custom"
down_revision: str | None = "011_add_system_settings"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add slack status customization columns to focus_settings."""
    op.add_column(
        "focus_settings",
        sa.Column("slack_status_text", sa.String(100), nullable=True),
    )
    op.add_column(
        "focus_settings",
        sa.Column("slack_status_emoji", sa.String(50), nullable=True),
    )
    op.add_column(
        "focus_settings",
        sa.Column("pomodoro_work_status_text", sa.String(100), nullable=True),
    )
    op.add_column(
        "focus_settings",
        sa.Column("pomodoro_work_status_emoji", sa.String(50), nullable=True),
    )
    op.add_column(
        "focus_settings",
        sa.Column("pomodoro_break_status_text", sa.String(100), nullable=True),
    )
    op.add_column(
        "focus_settings",
        sa.Column("pomodoro_break_status_emoji", sa.String(50), nullable=True),
    )


def downgrade() -> None:
    """Remove slack status customization columns from focus_settings."""
    op.drop_column("focus_settings", "pomodoro_break_status_emoji")
    op.drop_column("focus_settings", "pomodoro_break_status_text")
    op.drop_column("focus_settings", "pomodoro_work_status_emoji")
    op.drop_column("focus_settings", "pomodoro_work_status_text")
    op.drop_column("focus_settings", "slack_status_emoji")
    op.drop_column("focus_settings", "slack_status_text")
