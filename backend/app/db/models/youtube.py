from typing import TYPE_CHECKING

from sqlalchemy import Boolean, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.db.models.user import User


class YouTubePlaylist(Base, UUIDMixin, TimestampMixin):
    """YouTube playlist model."""

    __tablename__ = "youtube_playlists"

    user_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("users.id"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="youtube_playlists")
    videos: Mapped[list["YouTubeVideo"]] = relationship(
        "YouTubeVideo",
        back_populates="playlist",
        cascade="all, delete-orphan",
        order_by="YouTubeVideo.sort_order.asc()",
    )

    def __repr__(self) -> str:
        return f"<YouTubePlaylist(id={self.id}, name={self.name})>"


class YouTubeVideo(Base, UUIDMixin, TimestampMixin):
    """YouTube video model."""

    __tablename__ = "youtube_videos"

    playlist_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("youtube_playlists.id"), nullable=False
    )
    user_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("users.id"), nullable=False
    )
    youtube_url: Mapped[str] = mapped_column(String(500), nullable=False)
    youtube_video_id: Mapped[str] = mapped_column(String(20), nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    thumbnail_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="active", server_default="active")
    sort_order: Mapped[int] = mapped_column(Integer, default=0, server_default="0")

    # Relationships
    playlist: Mapped["YouTubePlaylist"] = relationship(
        "YouTubePlaylist", back_populates="videos"
    )
    user: Mapped["User"] = relationship("User", back_populates="youtube_videos")

    def __repr__(self) -> str:
        return f"<YouTubeVideo(id={self.id}, title={self.title})>"
