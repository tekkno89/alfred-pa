"""Add conversation_summary and summary_through_id to sessions.

Revision ID: 021_add_session_summary_fields
Revises: 020_add_youtube_playlist_archived
Create Date: 2026-03-19
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "021_add_session_summary_fields"
down_revision: str | None = "020_yt_playlist_archived"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add context window management columns to sessions."""
    op.add_column(
        "sessions",
        sa.Column("conversation_summary", sa.Text(), nullable=True),
    )
    op.add_column(
        "sessions",
        sa.Column(
            "summary_through_id",
            sa.dialects.postgresql.UUID(as_uuid=False),
            sa.ForeignKey("messages.id"),
            nullable=True,
        ),
    )


def downgrade() -> None:
    """Remove context window management columns from sessions."""
    op.drop_column("sessions", "summary_through_id")
    op.drop_column("sessions", "conversation_summary")
