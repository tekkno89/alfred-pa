"""YouTube API endpoints."""

from fastapi import APIRouter, HTTPException, Query, status

from app.api.deps import CurrentUser, DbSession
from app.db.repositories.dashboard import FeatureAccessRepository
from app.db.repositories.youtube import YouTubePlaylistRepository, YouTubeVideoRepository
from app.schemas.youtube import (
    YouTubeDashboardResponse,
    YouTubeMetadataResponse,
    YouTubePlaylistCreate,
    YouTubePlaylistListResponse,
    YouTubePlaylistResponse,
    YouTubePlaylistUpdate,
    YouTubeVideoCreate,
    YouTubeVideoListResponse,
    YouTubeVideoReorderRequest,
    YouTubeVideoResponse,
)
from app.services.youtube import YouTubeService

router = APIRouter()


async def _check_youtube_access(user: CurrentUser, db: DbSession) -> None:
    """Check that the user has card:youtube feature access."""
    if user.role == "admin":
        return
    repo = FeatureAccessRepository(db)
    if not await repo.is_enabled(user.id, "card:youtube"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="YouTube access not enabled",
        )


# --- Playlist endpoints ---


@router.get("/playlists", response_model=YouTubePlaylistListResponse)
async def list_playlists(
    db: DbSession,
    user: CurrentUser,
    include_archived: bool = Query(False),
) -> YouTubePlaylistListResponse:
    """List playlists for the current user."""
    await _check_youtube_access(user, db)
    repo = YouTubePlaylistRepository(db)
    playlists = await repo.get_user_playlists(user.id, include_archived=include_archived)
    return YouTubePlaylistListResponse(
        playlists=[YouTubePlaylistResponse.model_validate(p) for p in playlists]
    )


@router.post("/playlists", response_model=YouTubePlaylistResponse, status_code=status.HTTP_201_CREATED)
async def create_playlist(
    data: YouTubePlaylistCreate,
    db: DbSession,
    user: CurrentUser,
) -> YouTubePlaylistResponse:
    """Create a new playlist."""
    await _check_youtube_access(user, db)
    repo = YouTubePlaylistRepository(db)
    playlist = await repo.create_playlist(
        user_id=user.id,
        name=data.name,
        is_active=data.is_active,
    )
    return YouTubePlaylistResponse.model_validate(playlist)


@router.put("/playlists/{playlist_id}", response_model=YouTubePlaylistResponse)
async def update_playlist(
    playlist_id: str,
    data: YouTubePlaylistUpdate,
    db: DbSession,
    user: CurrentUser,
) -> YouTubePlaylistResponse:
    """Update a playlist."""
    await _check_youtube_access(user, db)
    repo = YouTubePlaylistRepository(db)
    playlist = await repo.get(playlist_id)

    if not playlist:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Playlist not found")
    if playlist.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized")

    updates = data.model_dump(exclude_none=True)
    if updates:
        playlist = await repo.update(playlist, **updates)

    return YouTubePlaylistResponse.model_validate(playlist)


@router.delete("/playlists/{playlist_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_playlist(
    playlist_id: str,
    db: DbSession,
    user: CurrentUser,
) -> None:
    """Delete a playlist and all its videos."""
    await _check_youtube_access(user, db)
    repo = YouTubePlaylistRepository(db)
    playlist = await repo.get(playlist_id)

    if not playlist:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Playlist not found")
    if playlist.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized")

    await repo.delete(playlist)


@router.patch("/playlists/{playlist_id}/activate", response_model=YouTubePlaylistResponse)
async def activate_playlist(
    playlist_id: str,
    db: DbSession,
    user: CurrentUser,
) -> YouTubePlaylistResponse:
    """Set a playlist as active."""
    await _check_youtube_access(user, db)
    repo = YouTubePlaylistRepository(db)
    playlist = await repo.set_active(user.id, playlist_id)

    if not playlist:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Playlist not found")

    return YouTubePlaylistResponse.model_validate(playlist)


@router.patch("/playlists/{playlist_id}/archive", response_model=YouTubePlaylistResponse)
async def archive_playlist(
    playlist_id: str,
    db: DbSession,
    user: CurrentUser,
) -> YouTubePlaylistResponse:
    """Archive a playlist."""
    await _check_youtube_access(user, db)
    repo = YouTubePlaylistRepository(db)
    playlist = await repo.get(playlist_id)

    if not playlist:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Playlist not found")
    if playlist.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized")

    playlist = await repo.update(playlist, is_archived=True, is_active=False)
    return YouTubePlaylistResponse.model_validate(playlist)


@router.patch("/playlists/{playlist_id}/unarchive", response_model=YouTubePlaylistResponse)
async def unarchive_playlist(
    playlist_id: str,
    db: DbSession,
    user: CurrentUser,
) -> YouTubePlaylistResponse:
    """Unarchive a playlist."""
    await _check_youtube_access(user, db)
    repo = YouTubePlaylistRepository(db)
    playlist = await repo.get(playlist_id)

    if not playlist:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Playlist not found")
    if playlist.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized")

    playlist = await repo.update(playlist, is_archived=False)
    return YouTubePlaylistResponse.model_validate(playlist)


# --- Video endpoints ---


@router.get("/playlists/{playlist_id}/videos", response_model=YouTubeVideoListResponse)
async def list_videos(
    playlist_id: str,
    db: DbSession,
    user: CurrentUser,
    status_filter: str | None = Query(None, alias="status"),
) -> YouTubeVideoListResponse:
    """List videos in a playlist."""
    await _check_youtube_access(user, db)
    video_repo = YouTubeVideoRepository(db)

    # "all" means no filter
    effective_status = status_filter if status_filter and status_filter != "all" else None

    videos = await video_repo.get_playlist_videos(playlist_id, user.id, effective_status)
    total = await video_repo.count_playlist_videos(playlist_id, user.id, effective_status)

    return YouTubeVideoListResponse(
        videos=[YouTubeVideoResponse.model_validate(v) for v in videos],
        total=total,
    )


@router.post("/videos", response_model=YouTubeVideoResponse, status_code=status.HTTP_201_CREATED)
async def add_video(
    data: YouTubeVideoCreate,
    db: DbSession,
    user: CurrentUser,
) -> YouTubeVideoResponse:
    """Add a video to a playlist. Backend fetches oEmbed metadata."""
    await _check_youtube_access(user, db)

    # Validate playlist ownership
    playlist_repo = YouTubePlaylistRepository(db)
    playlist = await playlist_repo.get(data.playlist_id)
    if not playlist or playlist.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Playlist not found")

    # Extract video ID
    video_id = YouTubeService.extract_video_id(data.youtube_url)
    if not video_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid YouTube URL",
        )

    # Fetch metadata
    metadata = await YouTubeService.fetch_metadata(data.youtube_url)

    video_repo = YouTubeVideoRepository(db)
    video = await video_repo.add_video(
        playlist_id=data.playlist_id,
        user_id=user.id,
        youtube_url=data.youtube_url,
        youtube_video_id=video_id,
        title=metadata["title"] or "Untitled",
        thumbnail_url=metadata["thumbnail_url"],
        add_to_top=data.add_to_top,
    )
    return YouTubeVideoResponse.model_validate(video)


@router.patch("/videos/{video_id}/watched", response_model=YouTubeVideoResponse)
async def mark_video_watched(
    video_id: str,
    db: DbSession,
    user: CurrentUser,
) -> YouTubeVideoResponse:
    """Mark a video as watched."""
    await _check_youtube_access(user, db)
    repo = YouTubeVideoRepository(db)
    video = await repo.get(video_id)

    if not video:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Video not found")
    if video.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized")

    video = await repo.mark_watched(video)
    return YouTubeVideoResponse.model_validate(video)


@router.patch("/videos/{video_id}/deleted", response_model=YouTubeVideoResponse)
async def mark_video_deleted(
    video_id: str,
    db: DbSession,
    user: CurrentUser,
) -> YouTubeVideoResponse:
    """Soft-delete a video."""
    await _check_youtube_access(user, db)
    repo = YouTubeVideoRepository(db)
    video = await repo.get(video_id)

    if not video:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Video not found")
    if video.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized")

    video = await repo.mark_deleted(video)
    return YouTubeVideoResponse.model_validate(video)


@router.patch("/videos/{video_id}/restore", response_model=YouTubeVideoResponse)
async def restore_video(
    video_id: str,
    db: DbSession,
    user: CurrentUser,
) -> YouTubeVideoResponse:
    """Restore a deleted video to active."""
    await _check_youtube_access(user, db)
    repo = YouTubeVideoRepository(db)
    video = await repo.get(video_id)

    if not video:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Video not found")
    if video.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized")

    video = await repo.restore_video(video)
    return YouTubeVideoResponse.model_validate(video)


@router.put("/playlists/{playlist_id}/reorder", status_code=status.HTTP_204_NO_CONTENT)
async def reorder_videos(
    playlist_id: str,
    data: YouTubeVideoReorderRequest,
    db: DbSession,
    user: CurrentUser,
) -> None:
    """Reorder videos in a playlist."""
    await _check_youtube_access(user, db)

    # Validate playlist ownership
    playlist_repo = YouTubePlaylistRepository(db)
    playlist = await playlist_repo.get(playlist_id)
    if not playlist or playlist.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Playlist not found")

    video_repo = YouTubeVideoRepository(db)
    await video_repo.reorder_videos(playlist_id, user.id, data.video_ids)


# --- Utility endpoints ---


@router.get("/metadata", response_model=YouTubeMetadataResponse)
async def fetch_metadata(
    user: CurrentUser,
    db: DbSession,
    url: str = Query(..., description="YouTube video URL"),
) -> YouTubeMetadataResponse:
    """Fetch oEmbed metadata for a YouTube URL."""
    await _check_youtube_access(user, db)

    video_id = YouTubeService.extract_video_id(url)
    metadata = await YouTubeService.fetch_metadata(url)

    return YouTubeMetadataResponse(
        title=metadata.get("title", ""),
        thumbnail_url=metadata.get("thumbnail_url"),
        youtube_video_id=video_id,
    )


@router.get("/dashboard", response_model=YouTubeDashboardResponse)
async def get_dashboard(
    db: DbSession,
    user: CurrentUser,
) -> YouTubeDashboardResponse:
    """Get dashboard card data."""
    await _check_youtube_access(user, db)
    video_repo = YouTubeVideoRepository(db)
    data = await video_repo.get_dashboard_data(user.id)

    current_video = None
    if data["current_video"]:
        current_video = YouTubeVideoResponse.model_validate(data["current_video"])

    return YouTubeDashboardResponse(
        playlist_name=data["playlist_name"],
        playlist_id=data["playlist_id"],
        current_video=current_video,
        active_video_count=data["active_video_count"],
    )
