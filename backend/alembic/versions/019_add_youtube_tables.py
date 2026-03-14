"""Add youtube_playlists and youtube_videos tables.

Revision ID: 019_add_youtube_tables
Revises: 018_add_session_type
Create Date: 2026-03-14
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "019_add_youtube_tables"
down_revision: str | None = "018_add_session_type"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create youtube_playlists and youtube_videos tables."""
    op.create_table(
        "youtube_playlists",
        sa.Column("id", sa.UUID(as_uuid=False), primary_key=True),
        sa.Column("user_id", sa.UUID(as_uuid=False), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("is_active", sa.Boolean, server_default="false", nullable=False),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_youtube_playlists_user_id", "youtube_playlists", ["user_id"])
    op.create_index("ix_youtube_playlists_user_id_is_active", "youtube_playlists", ["user_id", "is_active"])

    op.create_table(
        "youtube_videos",
        sa.Column("id", sa.UUID(as_uuid=False), primary_key=True),
        sa.Column("playlist_id", sa.UUID(as_uuid=False), sa.ForeignKey("youtube_playlists.id"), nullable=False),
        sa.Column("user_id", sa.UUID(as_uuid=False), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("youtube_url", sa.String(500), nullable=False),
        sa.Column("youtube_video_id", sa.String(20), nullable=False),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("thumbnail_url", sa.String(500), nullable=True),
        sa.Column("status", sa.String(20), server_default="active", nullable=False),
        sa.Column("sort_order", sa.Integer, server_default="0", nullable=False),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_youtube_videos_playlist_id", "youtube_videos", ["playlist_id"])
    op.create_index("ix_youtube_videos_user_id", "youtube_videos", ["user_id"])
    op.create_index(
        "ix_youtube_videos_playlist_status_sort",
        "youtube_videos",
        ["playlist_id", "status", "sort_order"],
    )


def downgrade() -> None:
    """Drop youtube_videos and youtube_playlists tables."""
    op.drop_index("ix_youtube_videos_playlist_status_sort", table_name="youtube_videos")
    op.drop_index("ix_youtube_videos_user_id", table_name="youtube_videos")
    op.drop_index("ix_youtube_videos_playlist_id", table_name="youtube_videos")
    op.drop_table("youtube_videos")
    op.drop_index("ix_youtube_playlists_user_id_is_active", table_name="youtube_playlists")
    op.drop_index("ix_youtube_playlists_user_id", table_name="youtube_playlists")
    op.drop_table("youtube_playlists")
