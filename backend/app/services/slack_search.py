"""Slack search service for message search and conversation reading."""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Any

from slack_sdk.errors import SlackApiError
from slack_sdk.web.async_client import AsyncWebClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.repositories import OAuthTokenRepository
from app.db.repositories.slack_search import (
    SlackChannelSummaryRepository,
    UserChannelParticipationRepository,
)
from app.services.token_encryption import TokenEncryptionService

logger = logging.getLogger(__name__)


class SlackSearchService:
    """Service for searching Slack messages and reading conversations."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.token_repo = OAuthTokenRepository(db)
        self.token_encryption = TokenEncryptionService(db)
        self.participation_repo = UserChannelParticipationRepository(db)
        self.summary_repo = SlackChannelSummaryRepository(db)
        # Cache user info lookups within a single service instance
        self._user_cache: dict[str, str] = {}

    async def _get_user_client(self, user_id: str) -> AsyncWebClient | None:
        """Get a Slack client using the user's OAuth token."""
        token = await self.token_repo.get_by_user_and_provider(user_id, "slack")
        if not token:
            return None
        access_token = await self.token_encryption.get_decrypted_access_token(token)
        return AsyncWebClient(token=access_token)

    async def _resolve_user_name(
        self, client: AsyncWebClient, slack_user_id: str
    ) -> str:
        """Resolve a Slack user ID to a display name, with caching."""
        if slack_user_id in self._user_cache:
            return self._user_cache[slack_user_id]
        try:
            resp = await client.users_info(user=slack_user_id)
            user = resp.get("user", {})
            name = (
                user.get("profile", {}).get("display_name")
                or user.get("profile", {}).get("real_name")
                or user.get("real_name")
                or slack_user_id
            )
            self._user_cache[slack_user_id] = name
            return name
        except SlackApiError:
            return slack_user_id

    async def search_messages(
        self,
        user_id: str,
        query: str,
        scope: str = "frequent",
        date_from: str | None = None,
        date_to: str | None = None,
        channel_ids: list[str] | None = None,
        max_results: int = 5,
    ) -> dict[str, Any]:
        """Search Slack messages using the search.messages API.

        Args:
            user_id: Alfred user ID
            query: Search text
            scope: "frequent" (top channels), "all" (everything), "archived" (include archived)
            date_from: YYYY-MM-DD start date
            date_to: YYYY-MM-DD end date
            channel_ids: Specific channel IDs to search in
            max_results: Maximum results to return
        """
        client = await self._get_user_client(user_id)
        if not client:
            return {"error": "no_token", "results": [], "total": 0}

        # Build search query with Slack modifiers
        search_query = query
        scope_channels: list[str] = []

        if channel_ids:
            # Explicit channel filter
            for cid in channel_ids:
                search_query += f" in:<#{cid}>"
            scope_channels = channel_ids
        elif scope == "frequent":
            # Search user's top channels
            top_channels = await self.participation_repo.get_by_user(
                user_id, limit=25
            )
            if top_channels:
                for ch in top_channels:
                    search_query += f" in:<#{ch.channel_id}>"
                scope_channels = [ch.channel_id for ch in top_channels]

        # Date filters
        if scope != "archived":
            if not date_from:
                # Default: last 30 days
                default_from = (datetime.utcnow() - timedelta(days=30)).strftime(
                    "%Y-%m-%d"
                )
                search_query += f" after:{default_from}"
            else:
                search_query += f" after:{date_from}"
        elif date_from:
            search_query += f" after:{date_from}"

        if date_to:
            search_query += f" before:{date_to}"

        try:
            response = await client.search_messages(
                query=search_query,
                sort="timestamp",
                sort_dir="desc",
                count=max_results,
            )

            messages = response.get("messages", {})
            matches = messages.get("matches", [])
            total = messages.get("total", 0)

            results = []
            for match in matches[:max_results]:
                results.append(
                    {
                        "channel_id": match.get("channel", {}).get("id", ""),
                        "channel_name": match.get("channel", {}).get("name", ""),
                        "sender_name": match.get("username", "unknown"),
                        "text_snippet": (match.get("text", "")[:300]),
                        "timestamp": match.get("ts", ""),
                        "date": _ts_to_date(match.get("ts", "")),
                        "permalink": match.get("permalink", ""),
                    }
                )

            return {
                "results": results,
                "total": total,
                "query": query,
                "scope": scope,
                "scope_channels": scope_channels,
            }

        except SlackApiError as e:
            error = e.response.get("error", "unknown")
            if error == "missing_scope":
                return {
                    "error": "missing_scope",
                    "message": "Slack search requires the search:read scope. Please re-authorize your Slack connection.",
                    "results": [],
                    "total": 0,
                }
            if error in ("paid_only", "not_allowed"):
                return {
                    "error": "paid_only",
                    "message": "Slack search is only available on paid Slack plans. Trying fallback search...",
                    "results": [],
                    "total": 0,
                }
            logger.error(f"Slack search error: {error}")
            return {"error": error, "results": [], "total": 0}

    async def search_history_fallback(
        self,
        user_id: str,
        query: str,
        channel_ids: list[str] | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
        max_results: int = 5,
    ) -> dict[str, Any]:
        """Fallback search using conversations.history with client-side filtering."""
        client = await self._get_user_client(user_id)
        if not client:
            return {"error": "no_token", "results": [], "total": 0}

        # Use provided channels or user's top channels
        if not channel_ids:
            channel_ids = await self.participation_repo.get_channel_ids_for_user(
                user_id, limit=10
            )
        else:
            channel_ids = channel_ids[:10]

        if not channel_ids:
            return {"results": [], "total": 0, "query": query, "scope": "fallback"}

        # Convert dates to timestamps
        oldest = None
        latest = None
        if date_from:
            try:
                oldest = str(
                    datetime.strptime(date_from, "%Y-%m-%d").timestamp()
                )
            except ValueError:
                pass
        if date_to:
            try:
                latest = str(
                    datetime.strptime(date_to, "%Y-%m-%d").timestamp()
                )
            except ValueError:
                pass

        query_lower = query.lower()
        results: list[dict[str, Any]] = []
        max_threads_per_channel = 5

        for channel_id in channel_ids:
            if len(results) >= max_results:
                break
            try:
                kwargs: dict[str, Any] = {
                    "channel": channel_id,
                    "limit": 100,
                }
                if oldest:
                    kwargs["oldest"] = oldest
                if latest:
                    kwargs["latest"] = latest

                response = await client.conversations_history(**kwargs)
                messages = response.get("messages", [])

                threads_checked = 0
                for msg in messages:
                    if len(results) >= max_results:
                        break
                    text = msg.get("text", "")
                    if query_lower in text.lower():
                        sender_id = msg.get("user", "")
                        sender_name = await self._resolve_user_name(
                            client, sender_id
                        ) if sender_id else "unknown"
                        results.append(
                            {
                                "channel_id": channel_id,
                                "channel_name": "",
                                "sender_name": sender_name,
                                "text_snippet": text[:300],
                                "timestamp": msg.get("ts", ""),
                                "date": _ts_to_date(msg.get("ts", "")),
                                "permalink": "",
                                "in_thread": False,
                            }
                        )

                    # Search thread replies for messages with threads
                    if (
                        msg.get("reply_count", 0) > 0
                        and threads_checked < max_threads_per_channel
                        and len(results) < max_results
                    ):
                        threads_checked += 1
                        try:
                            thread_resp = await client.conversations_replies(
                                channel=channel_id, ts=msg["ts"], limit=50
                            )
                            # Skip first message (parent, already checked above)
                            for reply in thread_resp.get("messages", [])[1:]:
                                if len(results) >= max_results:
                                    break
                                reply_text = reply.get("text", "")
                                if query_lower in reply_text.lower():
                                    reply_sender_id = reply.get("user", "")
                                    reply_sender_name = await self._resolve_user_name(
                                        client, reply_sender_id
                                    ) if reply_sender_id else "unknown"
                                    results.append(
                                        {
                                            "channel_id": channel_id,
                                            "channel_name": "",
                                            "sender_name": reply_sender_name,
                                            "text_snippet": reply_text[:300],
                                            "timestamp": reply.get("ts", ""),
                                            "date": _ts_to_date(reply.get("ts", "")),
                                            "permalink": "",
                                            "in_thread": True,
                                            "thread_ts": msg.get("ts", ""),
                                        }
                                    )
                        except SlackApiError:
                            pass

                # Rate limit spacing
                await asyncio.sleep(0.5)

            except SlackApiError as e:
                logger.warning(
                    f"Fallback search error for channel {channel_id}: {e.response.get('error', '')}"
                )
                continue

        return {
            "results": results,
            "total": len(results),
            "query": query,
            "scope": "fallback",
            "searched_channels": len(channel_ids),
            "note": (
                "This search used the fallback method (Slack free plan). "
                "Only top channels were searched with limited thread coverage. "
                "Ask the user for specific channels, DMs, or a timeframe to narrow the search."
            ),
        }

    async def get_search_context(self, user_id: str) -> list[dict[str, Any]]:
        """Get user's top channels with summaries for agent context."""
        channels = await self.participation_repo.get_by_user(user_id, limit=20)
        if not channels:
            return []

        channel_ids = [ch.channel_id for ch in channels]
        summaries = await self.summary_repo.get_by_channel_ids(channel_ids)
        summary_map = {s.channel_id: s.summary for s in summaries}

        result = []
        for ch in channels:
            result.append(
                {
                    "channel_id": ch.channel_id,
                    "channel_name": ch.channel_name,
                    "channel_type": ch.channel_type,
                    "member_count": ch.member_count,
                    "summary": summary_map.get(ch.channel_id, ""),
                    "rank": ch.participation_rank,
                }
            )
        return result

    async def get_messages(
        self,
        user_id: str,
        channel_id: str,
        thread_ts: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
        limit: int = 50,
        include_replies: bool = False,
    ) -> dict[str, Any]:
        """Retrieve conversation history from a channel, DM, or thread."""
        client = await self._get_user_client(user_id)
        if not client:
            return {"error": "no_token", "messages": [], "count": 0}

        limit = min(limit, 200)

        try:
            if thread_ts:
                # Get thread replies
                response = await client.conversations_replies(
                    channel=channel_id, ts=thread_ts, limit=limit
                )
                raw_messages = response.get("messages", [])
            else:
                # Get channel history
                kwargs: dict[str, Any] = {
                    "channel": channel_id,
                    "limit": limit,
                }
                if date_from:
                    try:
                        kwargs["oldest"] = str(
                            datetime.strptime(date_from, "%Y-%m-%d").timestamp()
                        )
                    except ValueError:
                        pass
                if date_to:
                    try:
                        kwargs["latest"] = str(
                            datetime.strptime(date_to, "%Y-%m-%d").timestamp()
                        )
                    except ValueError:
                        pass

                response = await client.conversations_history(**kwargs)
                raw_messages = response.get("messages", [])

            # Optionally fetch thread replies inline
            if include_replies and not thread_ts:
                expanded_messages = []
                for msg in raw_messages:
                    expanded_messages.append(msg)
                    if msg.get("reply_count", 0) > 0 and msg.get("ts"):
                        try:
                            thread_resp = await client.conversations_replies(
                                channel=channel_id, ts=msg["ts"], limit=50
                            )
                            replies = thread_resp.get("messages", [])
                            # Skip the first message (parent) to avoid duplication
                            for reply in replies[1:]:
                                reply["_is_reply"] = True
                                expanded_messages.append(reply)
                        except SlackApiError:
                            pass
                raw_messages = expanded_messages

            # Resolve sender names and format messages
            messages = []
            for msg in raw_messages:
                sender_id = msg.get("user", "")
                sender_name = await self._resolve_user_name(
                    client, sender_id
                ) if sender_id else "bot"
                messages.append(
                    {
                        "sender_name": sender_name,
                        "text": msg.get("text", ""),
                        "timestamp": msg.get("ts", ""),
                        "date": _ts_to_date(msg.get("ts", "")),
                        "thread_ts": msg.get("thread_ts"),
                        "reply_count": msg.get("reply_count", 0),
                        "is_reply": msg.get("_is_reply", False),
                    }
                )

            # Reverse to chronological order (history returns newest first)
            if not thread_ts:
                messages.reverse()

            # Get channel name
            channel_name = ""
            try:
                info_resp = await client.conversations_info(channel=channel_id)
                ch = info_resp.get("channel", {})
                channel_name = ch.get("name", ch.get("id", channel_id))
            except SlackApiError:
                channel_name = channel_id

            return {
                "messages": messages,
                "channel_id": channel_id,
                "channel_name": channel_name,
                "count": len(messages),
            }

        except SlackApiError as e:
            error = e.response.get("error", "unknown")
            logger.error(f"get_messages error: {error}")
            return {"error": error, "messages": [], "count": 0}

    async def resolve_channel_id(
        self, user_id: str, channel_name: str
    ) -> str | None:
        """Look up channel_id from participation data or channel cache."""
        # Strip # prefix if present
        channel_name = channel_name.lstrip("#")

        # Check participation data first
        participation = await self.participation_repo.get_by_channel_name(
            user_id, channel_name
        )
        if participation:
            return participation.channel_id

        # Fall back to SlackChannelCache (exact name match)
        from app.db.repositories.triage import SlackChannelCacheRepository

        cache_repo = SlackChannelCacheRepository(self.db)
        all_matches = await cache_repo.get_all(search=channel_name)
        for cached in all_matches:
            if cached.name == channel_name:
                return cached.slack_channel_id

        # Final fallback: direct Slack API lookup (handles unsynced private channels)
        client = await self._get_user_client(user_id)
        if client:
            try:
                cursor = None
                while True:
                    kwargs: dict[str, Any] = {
                        "types": "public_channel,private_channel",
                        "exclude_archived": True,
                        "limit": 200,
                    }
                    if cursor:
                        kwargs["cursor"] = cursor
                    response = await client.conversations_list(**kwargs)
                    for ch in response.get("channels", []):
                        if ch.get("name") == channel_name:
                            return ch["id"]
                    cursor = response.get("response_metadata", {}).get(
                        "next_cursor"
                    )
                    if not cursor:
                        break
            except SlackApiError as e:
                logger.warning(
                    f"Slack API fallback for channel resolution failed: "
                    f"{e.response.get('error', '')}"
                )

        return None

    async def list_user_channels(
        self, user_id: str, limit: int = 30
    ) -> list[dict[str, Any]]:
        """Get user's channels ranked by activity with summaries."""
        channels = await self.participation_repo.get_by_user(user_id, limit=limit)
        if not channels:
            return []

        channel_ids = [ch.channel_id for ch in channels]
        summaries = await self.summary_repo.get_by_channel_ids(channel_ids)
        summary_map = {s.channel_id: s.summary for s in summaries}

        result = []
        for ch in channels:
            result.append(
                {
                    "channel_id": ch.channel_id,
                    "channel_name": ch.channel_name,
                    "channel_type": ch.channel_type,
                    "member_count": ch.member_count,
                    "summary": summary_map.get(ch.channel_id, ""),
                    "rank": ch.participation_rank,
                }
            )
        return result

    async def find_channels(
        self, user_id: str, query: str, max_results: int = 10
    ) -> dict[str, Any]:
        """Search for channels by name via the live Slack API.

        Paginates through conversations_list and filters by substring match.
        Returns matching channels with metadata.
        """
        client = await self._get_user_client(user_id)
        if not client:
            return {"error": "no_token", "channels": []}

        query_lower = query.lower().lstrip("#")
        matches: list[dict[str, Any]] = []
        cursor = None

        try:
            while True:
                kwargs: dict[str, Any] = {
                    "types": "public_channel,private_channel",
                    "exclude_archived": True,
                    "limit": 200,
                }
                if cursor:
                    kwargs["cursor"] = cursor
                response = await client.conversations_list(**kwargs)

                for ch in response.get("channels", []):
                    name = ch.get("name", "")
                    if query_lower in name.lower():
                        channel_type = "private" if ch.get("is_private") else "public"
                        topic = ch.get("topic", {}).get("value", "")
                        purpose = ch.get("purpose", {}).get("value", "")
                        matches.append({
                            "channel_id": ch["id"],
                            "channel_name": name,
                            "channel_type": channel_type,
                            "is_member": ch.get("is_member", False),
                            "member_count": ch.get("num_members", 0),
                            "topic": topic,
                            "purpose": purpose,
                        })
                        if len(matches) >= max_results:
                            break

                if len(matches) >= max_results:
                    break

                cursor = response.get("response_metadata", {}).get("next_cursor")
                if not cursor:
                    break
        except SlackApiError as e:
            error = e.response.get("error", "unknown")
            logger.error(f"find_channels error: {error}")
            if not matches:
                return {"error": error, "channels": []}

        return {"channels": matches, "total": len(matches)}

    async def find_users(
        self, user_id: str, query: str, max_results: int = 10
    ) -> dict[str, Any]:
        """Search for Slack users by name via the live Slack API.

        Paginates through users_list and filters by substring match
        on display_name, real_name, or name fields.
        """
        client = await self._get_user_client(user_id)
        if not client:
            return {"error": "no_token", "users": []}

        query_lower = query.lower()
        matches: list[dict[str, Any]] = []
        cursor = None

        try:
            while True:
                kwargs: dict[str, Any] = {"limit": 200}
                if cursor:
                    kwargs["cursor"] = cursor
                response = await client.users_list(**kwargs)

                for user in response.get("members", []):
                    if user.get("deleted") or user.get("is_bot"):
                        continue

                    profile = user.get("profile", {})
                    display_name = profile.get("display_name", "")
                    real_name = profile.get("real_name") or user.get("real_name", "")
                    username = user.get("name", "")
                    title = profile.get("title", "")

                    if (
                        query_lower in display_name.lower()
                        or query_lower in real_name.lower()
                        or query_lower in username.lower()
                    ):
                        matches.append({
                            "user_id": user["id"],
                            "display_name": display_name or real_name,
                            "real_name": real_name,
                            "username": username,
                            "title": title,
                        })
                        if len(matches) >= max_results:
                            break

                if len(matches) >= max_results:
                    break

                cursor = response.get("response_metadata", {}).get("next_cursor")
                if not cursor:
                    break
        except SlackApiError as e:
            error = e.response.get("error", "unknown")
            logger.error(f"find_users error: {error}")
            if not matches:
                return {"error": error, "users": []}

        return {"users": matches, "total": len(matches)}


def _ts_to_date(ts: str) -> str:
    """Convert Slack timestamp to YYYY-MM-DD date string."""
    try:
        return datetime.fromtimestamp(float(ts)).strftime("%Y-%m-%d %H:%M")
    except (ValueError, TypeError, OSError):
        return ""
