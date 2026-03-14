"""YouTube management tool for the LLM agent."""

import logging
from typing import Any

from app.tools.base import BaseTool, ToolContext

logger = logging.getLogger(__name__)


class ManageYouTubeTool(BaseTool):
    """Tool for managing the user's YouTube watch queue via the LLM agent."""

    name = "manage_youtube"
    description = (
        "Manage the user's YouTube watch queue. Add videos by URL, list videos, "
        "mark videos as watched, create playlists, list playlists, or set the active playlist."
    )
    parameters_schema: dict[str, Any] = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": [
                    "add_video",
                    "list_videos",
                    "mark_watched",
                    "create_playlist",
                    "list_playlists",
                    "set_active_playlist",
                ],
                "description": "The YouTube action to perform.",
            },
            "youtube_url": {
                "type": "string",
                "description": "YouTube video URL (for add_video).",
            },
            "playlist_id": {
                "type": "string",
                "description": "Playlist ID. For add_video, defaults to active playlist if omitted.",
            },
            "playlist_name": {
                "type": "string",
                "description": "Name for a new playlist (for create_playlist).",
            },
            "video_id": {
                "type": "string",
                "description": "Video ID (for mark_watched).",
            },
            "add_to_top": {
                "type": "boolean",
                "description": "If true, add video to top of playlist (for add_video). Default false.",
            },
        },
        "required": ["action"],
    }

    async def execute(self, *, context: ToolContext | None = None, **kwargs: Any) -> str:
        """Execute a YouTube management action."""
        if not context or "user_id" not in context or "db" not in context:
            return "Error: YouTube management requires an authenticated session."

        user_id = context["user_id"]
        db = context["db"]
        action = kwargs.get("action", "")

        try:
            if action == "add_video":
                result = await self._handle_add_video(db, user_id, kwargs)
            elif action == "list_videos":
                result = await self._handle_list_videos(db, user_id, kwargs)
            elif action == "mark_watched":
                result = await self._handle_mark_watched(db, user_id, kwargs)
            elif action == "create_playlist":
                result = await self._handle_create_playlist(db, user_id, kwargs)
            elif action == "list_playlists":
                result = await self._handle_list_playlists(db, user_id)
            elif action == "set_active_playlist":
                result = await self._handle_set_active(db, user_id, kwargs)
            else:
                return f"Error: Unknown action '{action}'. Valid actions: add_video, list_videos, mark_watched, create_playlist, list_playlists, set_active_playlist."

            if action != "list_videos" and action != "list_playlists" and not result.startswith("Error"):
                try:
                    await db.commit()
                except Exception as e:
                    logger.error(f"YouTube commit failed: {e}")
                    return "Error: Failed to save changes."

            return result
        except Exception as e:
            logger.error(f"YouTube tool error: {e}")
            return f"Error performing YouTube action: {str(e)}"

    async def _handle_add_video(self, db: Any, user_id: str, kwargs: dict) -> str:
        from app.db.repositories.youtube import YouTubePlaylistRepository, YouTubeVideoRepository
        from app.services.youtube import YouTubeService

        url = kwargs.get("youtube_url", "")
        if not url:
            return "Error: youtube_url is required for add_video."

        video_id = YouTubeService.extract_video_id(url)
        if not video_id:
            return "Error: Invalid YouTube URL."

        playlist_id = kwargs.get("playlist_id")
        playlist_repo = YouTubePlaylistRepository(db)

        if not playlist_id:
            # Use active playlist
            active = await playlist_repo.get_active_playlist(user_id)
            if not active:
                # Create a default playlist
                active = await playlist_repo.create_playlist(user_id, "Watch Later", is_active=True)
            playlist_id = active.id
        else:
            playlist = await playlist_repo.get(playlist_id)
            if not playlist or playlist.user_id != user_id:
                return "Error: Playlist not found."

        metadata = await YouTubeService.fetch_metadata(url)
        video_repo = YouTubeVideoRepository(db)
        add_to_top = kwargs.get("add_to_top", False)

        video = await video_repo.add_video(
            playlist_id=playlist_id,
            user_id=user_id,
            youtube_url=url,
            youtube_video_id=video_id,
            title=metadata["title"] or "Untitled",
            thumbnail_url=metadata["thumbnail_url"],
            add_to_top=add_to_top,
        )

        self.last_execution_metadata = {
            "action": "add_video",
            "title": video.title,
            "video_id": video.id,
        }

        return f'Added "{video.title}" to the watch queue.'

    async def _handle_list_videos(self, db: Any, user_id: str, kwargs: dict) -> str:
        from app.db.repositories.youtube import YouTubePlaylistRepository, YouTubeVideoRepository

        playlist_id = kwargs.get("playlist_id")
        playlist_repo = YouTubePlaylistRepository(db)

        if not playlist_id:
            active = await playlist_repo.get_active_playlist(user_id)
            if not active:
                return "No active playlist. Create one first."
            playlist_id = active.id
            playlist_name = active.name
        else:
            playlist = await playlist_repo.get(playlist_id)
            if not playlist or playlist.user_id != user_id:
                return "Error: Playlist not found."
            playlist_name = playlist.name

        video_repo = YouTubeVideoRepository(db)
        videos = await video_repo.get_playlist_videos(playlist_id, user_id, status="active")

        if not videos:
            return f'No unwatched videos in "{playlist_name}".'

        lines = [f'Unwatched videos in "{playlist_name}" ({len(videos)} total):']
        for i, v in enumerate(videos, 1):
            lines.append(f"{i}. {v.title} — {v.youtube_url}")

        return "\n".join(lines)

    async def _handle_mark_watched(self, db: Any, user_id: str, kwargs: dict) -> str:
        from app.db.repositories.youtube import YouTubeVideoRepository

        vid = kwargs.get("video_id", "")
        if not vid:
            return "Error: video_id is required for mark_watched."

        repo = YouTubeVideoRepository(db)
        video = await repo.get(vid)
        if not video or video.user_id != user_id:
            return "Error: Video not found."

        await repo.mark_watched(video)

        self.last_execution_metadata = {
            "action": "mark_watched",
            "title": video.title,
        }

        return f'Marked "{video.title}" as watched.'

    async def _handle_create_playlist(self, db: Any, user_id: str, kwargs: dict) -> str:
        from app.db.repositories.youtube import YouTubePlaylistRepository

        name = kwargs.get("playlist_name", "")
        if not name:
            return "Error: playlist_name is required for create_playlist."

        repo = YouTubePlaylistRepository(db)
        playlist = await repo.create_playlist(user_id, name, is_active=True)

        self.last_execution_metadata = {
            "action": "create_playlist",
            "playlist_name": playlist.name,
            "playlist_id": playlist.id,
        }

        return f'Created playlist "{playlist.name}" and set it as active.'

    async def _handle_list_playlists(self, db: Any, user_id: str) -> str:
        from app.db.repositories.youtube import YouTubePlaylistRepository

        repo = YouTubePlaylistRepository(db)
        playlists = await repo.get_user_playlists(user_id)

        if not playlists:
            return "No playlists found. Use create_playlist to create one."

        lines = ["Your YouTube playlists:"]
        for p in playlists:
            active_marker = " (active)" if p.is_active else ""
            lines.append(f"- {p.name}{active_marker} (ID: {p.id})")

        return "\n".join(lines)

    async def _handle_set_active(self, db: Any, user_id: str, kwargs: dict) -> str:
        from app.db.repositories.youtube import YouTubePlaylistRepository

        playlist_id = kwargs.get("playlist_id", "")
        if not playlist_id:
            return "Error: playlist_id is required for set_active_playlist."

        repo = YouTubePlaylistRepository(db)
        playlist = await repo.set_active(user_id, playlist_id)
        if not playlist:
            return "Error: Playlist not found."

        return f'Set "{playlist.name}" as the active playlist.'
