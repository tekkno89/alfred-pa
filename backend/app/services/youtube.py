"""YouTube service for metadata extraction via oEmbed."""

import logging
import re
from urllib.parse import parse_qs, urlparse

import httpx

logger = logging.getLogger(__name__)

OEMBED_URL = "https://www.youtube.com/oembed"


class YouTubeService:
    """Service for extracting YouTube video metadata."""

    @staticmethod
    def extract_video_id(url: str) -> str | None:
        """Extract the YouTube video ID from various URL formats.

        Supports:
        - https://www.youtube.com/watch?v=VIDEO_ID
        - https://youtu.be/VIDEO_ID
        - https://www.youtube.com/embed/VIDEO_ID
        - https://youtube.com/shorts/VIDEO_ID
        """
        if not url:
            return None

        parsed = urlparse(url)

        # youtu.be/VIDEO_ID
        if parsed.hostname in ("youtu.be",):
            return parsed.path.lstrip("/").split("/")[0] or None

        # youtube.com variants
        if parsed.hostname in ("www.youtube.com", "youtube.com", "m.youtube.com"):
            # /watch?v=VIDEO_ID
            if parsed.path == "/watch":
                qs = parse_qs(parsed.query)
                v = qs.get("v")
                return v[0] if v else None

            # /embed/VIDEO_ID or /shorts/VIDEO_ID
            match = re.match(r"^/(embed|shorts)/([^/?&]+)", parsed.path)
            if match:
                return match.group(2)

        return None

    @staticmethod
    async def fetch_metadata(url: str) -> dict[str, str | None]:
        """Fetch video metadata via YouTube oEmbed API.

        Returns dict with title and thumbnail_url.
        """
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(
                    OEMBED_URL,
                    params={"url": url, "format": "json"},
                )
                resp.raise_for_status()
                data = resp.json()
                return {
                    "title": data.get("title", ""),
                    "thumbnail_url": data.get("thumbnail_url"),
                }
        except Exception as e:
            logger.warning("Failed to fetch YouTube oEmbed metadata for %s: %s", url, e)
            return {"title": "", "thumbnail_url": None}
