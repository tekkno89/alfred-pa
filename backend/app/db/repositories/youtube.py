"""YouTube playlist and video repositories."""

from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.youtube import YouTubePlaylist, YouTubeVideo
from app.db.repositories.base import BaseRepository


class YouTubePlaylistRepository(BaseRepository[YouTubePlaylist]):
    """Repository for YouTubePlaylist model."""

    def __init__(self, db: AsyncSession):
        super().__init__(YouTubePlaylist, db)

    async def get_user_playlists(
        self, user_id: str, *, include_archived: bool = False
    ) -> list[YouTubePlaylist]:
        """Get playlists for a user, ordered by name."""
        query = select(YouTubePlaylist).where(YouTubePlaylist.user_id == user_id)
        if not include_archived:
            query = query.where(YouTubePlaylist.is_archived == False)  # noqa: E712
        query = query.order_by(YouTubePlaylist.name.asc())
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def get_active_playlist(self, user_id: str) -> YouTubePlaylist | None:
        """Get the active playlist for a user."""
        result = await self.db.execute(
            select(YouTubePlaylist).where(
                YouTubePlaylist.user_id == user_id,
                YouTubePlaylist.is_active == True,  # noqa: E712
            )
        )
        return result.scalar_one_or_none()

    async def set_active(self, user_id: str, playlist_id: str) -> YouTubePlaylist | None:
        """Deactivate all playlists, then activate the specified one."""
        # Deactivate all
        await self.db.execute(
            update(YouTubePlaylist)
            .where(YouTubePlaylist.user_id == user_id)
            .values(is_active=False)
        )
        # Activate the specified playlist
        result = await self.db.execute(
            select(YouTubePlaylist).where(
                YouTubePlaylist.id == playlist_id,
                YouTubePlaylist.user_id == user_id,
            )
        )
        playlist = result.scalar_one_or_none()
        if playlist:
            playlist.is_active = True
            await self.db.flush()
            await self.db.refresh(playlist)
        return playlist

    async def create_playlist(
        self,
        user_id: str,
        name: str,
        is_active: bool = False,
    ) -> YouTubePlaylist:
        """Create a playlist. If is_active, deactivate others first."""
        if is_active:
            await self.db.execute(
                update(YouTubePlaylist)
                .where(YouTubePlaylist.user_id == user_id)
                .values(is_active=False)
            )
        playlist = YouTubePlaylist(
            user_id=user_id,
            name=name,
            is_active=is_active,
        )
        return await self.create(playlist)


class YouTubeVideoRepository(BaseRepository[YouTubeVideo]):
    """Repository for YouTubeVideo model."""

    def __init__(self, db: AsyncSession):
        super().__init__(YouTubeVideo, db)

    async def get_playlist_videos(
        self,
        playlist_id: str,
        user_id: str,
        status: str | None = None,
    ) -> list[YouTubeVideo]:
        """Get videos in a playlist, ordered by sort_order."""
        query = select(YouTubeVideo).where(
            YouTubeVideo.playlist_id == playlist_id,
            YouTubeVideo.user_id == user_id,
        )
        if status:
            query = query.where(YouTubeVideo.status == status)
        query = query.order_by(YouTubeVideo.sort_order.asc())
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def count_playlist_videos(
        self,
        playlist_id: str,
        user_id: str,
        status: str | None = None,
    ) -> int:
        """Count videos in a playlist."""
        query = (
            select(func.count())
            .select_from(YouTubeVideo)
            .where(
                YouTubeVideo.playlist_id == playlist_id,
                YouTubeVideo.user_id == user_id,
            )
        )
        if status:
            query = query.where(YouTubeVideo.status == status)
        result = await self.db.execute(query)
        return result.scalar() or 0

    async def get_next_unwatched(
        self, playlist_id: str, user_id: str
    ) -> YouTubeVideo | None:
        """Get the first active video by sort_order."""
        result = await self.db.execute(
            select(YouTubeVideo)
            .where(
                YouTubeVideo.playlist_id == playlist_id,
                YouTubeVideo.user_id == user_id,
                YouTubeVideo.status == "active",
            )
            .order_by(YouTubeVideo.sort_order.asc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def get_max_sort_order(self, playlist_id: str) -> int:
        """Get the maximum sort_order in a playlist."""
        result = await self.db.execute(
            select(func.max(YouTubeVideo.sort_order)).where(
                YouTubeVideo.playlist_id == playlist_id
            )
        )
        return result.scalar() or 0

    async def add_video(
        self,
        playlist_id: str,
        user_id: str,
        youtube_url: str,
        youtube_video_id: str,
        title: str,
        thumbnail_url: str | None = None,
        add_to_top: bool = False,
    ) -> YouTubeVideo:
        """Add a video to a playlist."""
        if add_to_top:
            # Shift all existing sort_orders up by 1
            await self.db.execute(
                update(YouTubeVideo)
                .where(YouTubeVideo.playlist_id == playlist_id)
                .values(sort_order=YouTubeVideo.sort_order + 1)
            )
            sort_order = 0
        else:
            sort_order = await self.get_max_sort_order(playlist_id) + 1

        video = YouTubeVideo(
            playlist_id=playlist_id,
            user_id=user_id,
            youtube_url=youtube_url,
            youtube_video_id=youtube_video_id,
            title=title,
            thumbnail_url=thumbnail_url,
            sort_order=sort_order,
        )
        return await self.create(video)

    async def mark_watched(self, video: YouTubeVideo) -> YouTubeVideo:
        """Mark a video as watched."""
        return await self.update(video, status="watched")

    async def mark_deleted(self, video: YouTubeVideo) -> YouTubeVideo:
        """Soft-delete a video."""
        return await self.update(video, status="deleted")

    async def restore_video(self, video: YouTubeVideo) -> YouTubeVideo:
        """Restore a video to active status."""
        return await self.update(video, status="active")

    async def reorder_videos(
        self, playlist_id: str, user_id: str, video_ids: list[str]
    ) -> None:
        """Set sort_order = index for each video ID."""
        for index, video_id in enumerate(video_ids):
            await self.db.execute(
                update(YouTubeVideo)
                .where(
                    YouTubeVideo.id == video_id,
                    YouTubeVideo.playlist_id == playlist_id,
                    YouTubeVideo.user_id == user_id,
                )
                .values(sort_order=index)
            )
        await self.db.flush()

    async def get_dashboard_data(self, user_id: str) -> dict[str, Any]:
        """Get dashboard card data: active playlist + first unwatched video + count."""
        # Find active playlist
        playlist_result = await self.db.execute(
            select(YouTubePlaylist).where(
                YouTubePlaylist.user_id == user_id,
                YouTubePlaylist.is_active == True,  # noqa: E712
            )
        )
        playlist = playlist_result.scalar_one_or_none()

        if not playlist:
            return {
                "playlist_name": None,
                "playlist_id": None,
                "current_video": None,
                "active_video_count": 0,
            }

        # Get first unwatched video
        video = await self.get_next_unwatched(playlist.id, user_id)
        active_count = await self.count_playlist_videos(
            playlist.id, user_id, status="active"
        )

        return {
            "playlist_name": playlist.name,
            "playlist_id": playlist.id,
            "current_video": video,
            "active_video_count": active_count,
        }
