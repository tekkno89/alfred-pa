"""Add is_archived column to youtube_playlists.

Revision ID: 020_yt_playlist_archived
Revises: 019_add_youtube_tables
Create Date: 2026-03-14
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "020_yt_playlist_archived"
down_revision: str | None = "019_add_youtube_tables"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add is_archived column to youtube_playlists."""
    op.add_column(
        "youtube_playlists",
        sa.Column("is_archived", sa.Boolean, server_default="false", nullable=False),
    )


def downgrade() -> None:
    """Remove is_archived column from youtube_playlists."""
    op.drop_column("youtube_playlists", "is_archived")
