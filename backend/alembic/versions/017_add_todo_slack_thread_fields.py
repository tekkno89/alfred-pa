"""Add Slack reminder thread fields to todos.

Revision ID: 017_add_todo_slack_thread_fields
Revises: 016_add_todos_table
Create Date: 2026-03-04
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "017_add_todo_slack_thread_fields"
down_revision: str | None = "016_add_todos_table"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add slack_reminder_thread_ts and slack_reminder_channel to todos."""
    op.add_column(
        "todos",
        sa.Column("slack_reminder_thread_ts", sa.String(50), nullable=True),
    )
    op.add_column(
        "todos",
        sa.Column("slack_reminder_channel", sa.String(50), nullable=True),
    )


def downgrade() -> None:
    """Remove slack_reminder_thread_ts and slack_reminder_channel from todos."""
    op.drop_column("todos", "slack_reminder_channel")
    op.drop_column("todos", "slack_reminder_thread_ts")
