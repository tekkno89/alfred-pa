"""YouTube schemas for API request/response."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict


# --- Playlist schemas ---


class YouTubePlaylistCreate(BaseModel):
    """Schema for creating a YouTube playlist."""

    name: str
    is_active: bool = False


class YouTubePlaylistUpdate(BaseModel):
    """Schema for updating a YouTube playlist."""

    name: str | None = None
    is_active: bool | None = None


class YouTubePlaylistResponse(BaseModel):
    """Schema for playlist response."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    is_active: bool
    is_archived: bool
    created_at: datetime
    updated_at: datetime


class YouTubePlaylistListResponse(BaseModel):
    """Schema for playlist list."""

    playlists: list[YouTubePlaylistResponse]


# --- Video schemas ---


class YouTubeVideoCreate(BaseModel):
    """Schema for adding a video."""

    playlist_id: str
    youtube_url: str
    add_to_top: bool = False


class YouTubeVideoUpdate(BaseModel):
    """Schema for updating a video."""

    status: str | None = None


class YouTubeVideoResponse(BaseModel):
    """Schema for video response."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    playlist_id: str
    youtube_url: str
    youtube_video_id: str
    title: str
    thumbnail_url: str | None
    status: str
    sort_order: int
    created_at: datetime
    updated_at: datetime


class YouTubeVideoListResponse(BaseModel):
    """Schema for video list."""

    videos: list[YouTubeVideoResponse]
    total: int


# --- Utility schemas ---


class YouTubeVideoReorderRequest(BaseModel):
    """Schema for reordering videos."""

    video_ids: list[str]


class YouTubeMetadataResponse(BaseModel):
    """Schema for oEmbed metadata response."""

    title: str
    thumbnail_url: str | None
    youtube_video_id: str | None


class YouTubeDashboardResponse(BaseModel):
    """Schema for dashboard card data."""

    playlist_name: str | None = None
    playlist_id: str | None = None
    current_video: YouTubeVideoResponse | None = None
    active_video_count: int = 0
