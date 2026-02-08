"""Add pomodoro session configuration columns.

Revision ID: 005
Revises: 004
Create Date: 2026-02-08
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "005_add_pomodoro_session_config"
down_revision: str | None = "004_add_focus_mode_tables"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Add pomodoro session configuration columns to focus_mode_state
    op.add_column(
        "focus_mode_state",
        sa.Column("pomodoro_total_sessions", sa.Integer(), nullable=True),
    )
    op.add_column(
        "focus_mode_state",
        sa.Column("pomodoro_work_minutes", sa.Integer(), nullable=True),
    )
    op.add_column(
        "focus_mode_state",
        sa.Column("pomodoro_break_minutes", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("focus_mode_state", "pomodoro_break_minutes")
    op.drop_column("focus_mode_state", "pomodoro_work_minutes")
    op.drop_column("focus_mode_state", "pomodoro_total_sessions")
