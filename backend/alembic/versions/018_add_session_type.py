"""Add session_type column to sessions.

Revision ID: 018_add_session_type
Revises: 017_add_todo_slack_thread_fields
Create Date: 2026-03-05
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "018_add_session_type"
down_revision: str | None = "017_add_todo_slack_thread_fields"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add session_type column and backfill existing rows to 'conversation'."""
    op.add_column(
        "sessions",
        sa.Column("session_type", sa.String(20), nullable=True),
    )
    # Backfill all existing sessions as conversations
    op.execute("UPDATE sessions SET session_type = 'conversation'")


def downgrade() -> None:
    """Remove session_type column from sessions."""
    op.drop_column("sessions", "session_type")
