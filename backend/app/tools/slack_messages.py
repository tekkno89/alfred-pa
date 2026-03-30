"""Slack messages tool for searching, reading, and listing channels."""

import logging
from typing import Any

from app.tools.base import BaseTool, ToolContext

logger = logging.getLogger(__name__)


class SlackMessagesTool(BaseTool):
    """Tool for searching Slack messages, reading conversations, and listing channels."""

    name = "slack_messages"
    max_iterations = 5
    description = (
        "Search Slack messages, read channel/DM conversations, or list channels. "
        'Actions: "search" finds messages matching a query, '
        '"get_messages" retrieves conversation history from a channel/DM/thread, '
        '"list_channels" shows the user\'s channels with summaries.'
    )
    parameters_schema: dict[str, Any] = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["search", "get_messages", "top_channels", "find_channel", "find_user"],
                "description": "Action to perform.",
            },
            "query": {
                "type": "string",
                "description": "(search) Search text.",
            },
            "scope": {
                "type": "string",
                "enum": ["frequent", "all", "archived"],
                "description": "(search) Search scope. 'frequent' searches top channels, 'all' searches everything.",
            },
            "channel_id": {
                "type": "string",
                "description": "(get_messages) Slack channel/DM ID to read.",
            },
            "channel_name": {
                "type": "string",
                "description": "(get_messages/search) Channel name to look up (alternative to channel_id).",
            },
            "thread_ts": {
                "type": "string",
                "description": "(get_messages) Thread timestamp to get replies for a specific thread.",
            },
            "date_from": {
                "type": "string",
                "description": "(search/get_messages) YYYY-MM-DD start date.",
            },
            "date_to": {
                "type": "string",
                "description": "(search/get_messages) YYYY-MM-DD end date.",
            },
            "limit": {
                "type": "integer",
                "description": "(get_messages) Max messages to retrieve (default 50, max 200).",
            },
            "channel_ids": {
                "type": "array",
                "items": {"type": "string"},
                "description": "(search) Specific channel IDs to search in.",
            },
            "use_fallback": {
                "type": "boolean",
                "description": "(search) Also try conversations.history fallback if primary search fails.",
            },
            "include_replies": {
                "type": "boolean",
                "description": "(get_messages) Include thread replies inline (default false).",
            },
        },
        "required": ["action"],
    }

    async def execute(self, *, context: ToolContext | None = None, **kwargs: Any) -> str:
        """Execute a Slack messages action."""
        if not context or "user_id" not in context or "db" not in context:
            return "Error: Slack messages requires an authenticated session."

        user_id = context["user_id"]
        db = context["db"]
        action = kwargs.get("action", "")

        try:
            if action == "search":
                return await self._handle_search(db, user_id, kwargs)
            elif action == "get_messages":
                return await self._handle_get_messages(db, user_id, kwargs)
            elif action == "top_channels":
                return await self._handle_top_channels(db, user_id, kwargs)
            elif action == "find_channel":
                return await self._handle_find_channel(db, user_id, kwargs)
            elif action == "find_user":
                return await self._handle_find_user(db, user_id, kwargs)
            else:
                return f"Error: Unknown action '{action}'. Use search, get_messages, top_channels, find_channel, or find_user."
        except Exception as e:
            logger.error(f"Slack messages tool error (action={action}): {e}", exc_info=True)
            return f"Error performing Slack {action}: {str(e)}"

    async def _handle_search(self, db, user_id: str, kwargs: dict) -> str:
        from app.services.slack_search import SlackSearchService

        query = kwargs.get("query")
        if not query:
            return "Error: 'query' is required for search."

        service = SlackSearchService(db)

        # Check for Slack OAuth
        from app.services.slack_user import SlackUserService

        slack_user = SlackUserService(db)
        if not await slack_user.has_oauth_token(user_id):
            return (
                "You haven't connected your Slack account yet. "
                "Go to Settings > Integrations to connect Slack, then I can search your messages."
            )

        scope = kwargs.get("scope", "frequent")
        result = await service.search_messages(
            user_id=user_id,
            query=query,
            scope=scope,
            date_from=kwargs.get("date_from"),
            date_to=kwargs.get("date_to"),
            channel_ids=kwargs.get("channel_ids"),
            max_results=5,
        )

        # Handle errors
        if result.get("error") == "no_token":
            return "You haven't connected your Slack account. Go to Settings > Integrations to connect."
        if result.get("error") == "missing_scope":
            return result.get("message", "Missing Slack search scope. Please re-authorize.")
        if result.get("error") == "paid_only":
            # Auto-fallback for free Slack plans
            logger.info("Search API unavailable (paid only), trying fallback")
            result = await service.search_history_fallback(
                user_id=user_id,
                query=query,
                channel_ids=kwargs.get("channel_ids"),
                date_from=kwargs.get("date_from"),
                date_to=kwargs.get("date_to"),
            )

        # If no results from primary search, try fallback if requested
        if not result.get("results") and kwargs.get("use_fallback") and result.get("scope") != "fallback":
            fallback = await service.search_history_fallback(
                user_id=user_id,
                query=query,
                channel_ids=kwargs.get("channel_ids"),
                date_from=kwargs.get("date_from"),
                date_to=kwargs.get("date_to"),
            )
            if fallback.get("results"):
                result = fallback

        is_fallback = result.get("scope") == "fallback"
        results = result.get("results", [])

        if not results:
            suggestion = f'No results found for "{query}"'
            if is_fallback:
                searched = result.get("searched_channels", 0)
                suggestion += (
                    f". This used a limited fallback search across {searched} of the user's top channels "
                    "(Slack free plan — full search API is unavailable). "
                    "Ask the user which specific channels, DMs, or group messages to check, "
                    "and a timeframe. Then use get_messages on those channels to search more thoroughly."
                )
            elif scope == "frequent":
                suggestion += " in your frequent channels. Try scope='all' to search all channels."
            elif not kwargs.get("date_from"):
                suggestion += ". Try specifying a date range or different search terms."
            return suggestion

        # Format results
        self.last_execution_metadata = {
            "query": query,
            "result_count": len(results),
            "scope": result.get("scope", scope),
        }

        if len(results) == 1:
            r = results[0]
            thread_label = " (in a thread)" if r.get("in_thread") else ""
            lines = [
                f"Found a message in #{r['channel_name'] or r['channel_id']}{thread_label}:",
                f"From: {r['sender_name']} ({r['date']})",
                f"Message: {r['text_snippet']}",
            ]
            if r.get("permalink"):
                lines.append(f"Link: {r['permalink']}")
            if is_fallback:
                lines.append(self._fallback_note(result))
            return "\n".join(lines)

        lines = [f'Found {result.get("total", len(results))} results for "{query}":']
        for i, r in enumerate(results, 1):
            channel = r.get("channel_name") or r.get("channel_id", "")
            thread_label = " (thread)" if r.get("in_thread") else ""
            lines.append(
                f"\n{i}. #{channel} — {r['sender_name']} ({r['date']}){thread_label}"
            )
            lines.append(f"   {r['text_snippet'][:200]}")
            if r.get("permalink"):
                lines.append(f"   Link: {r['permalink']}")

        if is_fallback:
            lines.append(self._fallback_note(result))

        return "\n".join(lines)

    @staticmethod
    def _fallback_note(result: dict) -> str:
        searched = result.get("searched_channels", 0)
        return (
            f"\n⚠ Limited search: This used a fallback method (Slack free plan) across {searched} "
            "top channels with limited thread coverage. If the message wasn't found, ask the user "
            "for specific channels, DMs, or a timeframe, then use get_messages to search those directly."
        )

    async def _handle_get_messages(self, db, user_id: str, kwargs: dict) -> str:
        from app.services.slack_search import SlackSearchService

        service = SlackSearchService(db)

        # Resolve channel
        channel_id = kwargs.get("channel_id")
        channel_name = kwargs.get("channel_name")

        if not channel_id and not channel_name:
            return "Error: Either 'channel_id' or 'channel_name' is required."

        if not channel_id and channel_name:
            channel_id = await service.resolve_channel_id(user_id, channel_name)
            if not channel_id:
                return f"Could not find a channel named '#{channel_name}'. Use action='list_channels' to see available channels."

        # Check OAuth
        from app.services.slack_user import SlackUserService

        slack_user = SlackUserService(db)
        if not await slack_user.has_oauth_token(user_id):
            return "You haven't connected your Slack account. Go to Settings > Integrations to connect."

        result = await service.get_messages(
            user_id=user_id,
            channel_id=channel_id,
            thread_ts=kwargs.get("thread_ts"),
            date_from=kwargs.get("date_from"),
            date_to=kwargs.get("date_to"),
            limit=kwargs.get("limit", 50),
            include_replies=kwargs.get("include_replies", False),
        )

        if result.get("error") == "no_token":
            return "You haven't connected your Slack account. Go to Settings > Integrations to connect."
        if result.get("error"):
            return f"Error reading channel: {result['error']}"

        messages = result.get("messages", [])
        if not messages:
            return f"No messages found in #{result.get('channel_name', channel_id)}."

        self.last_execution_metadata = {
            "channel_name": result.get("channel_name", ""),
            "message_count": len(messages),
        }

        # Format conversation
        ch_name = result.get("channel_name", channel_id)
        lines = [f"Conversation in #{ch_name} ({len(messages)} messages):"]

        for msg in messages:
            prefix = "  ↳ " if msg.get("is_reply") else ""
            thread_info = ""
            if msg.get("reply_count", 0) > 0 and not msg.get("is_reply"):
                thread_info = f" [{msg['reply_count']} replies]"
            lines.append(
                f"\n{prefix}{msg['sender_name']} ({msg['date']}){thread_info}:"
            )
            lines.append(f"{prefix}{msg['text']}")

        return "\n".join(lines)

    async def _handle_top_channels(self, db, user_id: str, kwargs: dict) -> str:
        from app.services.slack_search import SlackSearchService

        service = SlackSearchService(db)

        # Check OAuth
        from app.services.slack_user import SlackUserService

        slack_user = SlackUserService(db)
        if not await slack_user.has_oauth_token(user_id):
            return "You haven't connected your Slack account. Go to Settings > Integrations to connect."

        channels = await service.list_user_channels(user_id, limit=30)
        if not channels:
            return (
                "No channel data available yet. Top channel data is updated daily — "
                "it may not be ready if you just connected Slack. "
                "Use action='find_channel' to search for a specific channel by name."
            )

        lines = [f"Your top {len(channels)} most active Slack channels:"]
        for ch in channels:
            type_label = {"public": "public", "private": "private", "mpim": "group DM", "im": "DM"}.get(
                ch["channel_type"], ch["channel_type"]
            )
            summary = f" — {ch['summary']}" if ch.get("summary") else ""
            if ch["channel_type"] == "im":
                lines.append(
                    f"\n• {ch['channel_name']} ({type_label}){summary}"
                )
            else:
                lines.append(
                    f"\n• #{ch['channel_name']} ({type_label}, {ch['member_count']} members){summary}"
                )
            lines.append(f"  ID: {ch['channel_id']}")

        lines.append(
            "\nNote: This shows your most active channels only. "
            "Use action='find_channel' to search for any channel by name."
        )
        return "\n".join(lines)

    async def _handle_find_channel(self, db, user_id: str, kwargs: dict) -> str:
        from app.services.slack_search import SlackSearchService
        from app.services.slack_user import SlackUserService

        channel_name = kwargs.get("channel_name") or kwargs.get("query")
        if not channel_name:
            return "Error: 'channel_name' (or 'query') is required for find_channel."

        slack_user = SlackUserService(db)
        if not await slack_user.has_oauth_token(user_id):
            return "You haven't connected your Slack account. Go to Settings > Integrations to connect."

        service = SlackSearchService(db)
        result = await service.find_channels(user_id=user_id, query=channel_name)

        if result.get("error") == "no_token":
            return "You haven't connected your Slack account. Go to Settings > Integrations to connect."
        if result.get("error"):
            return f"Error searching channels: {result['error']}"

        channels = result.get("channels", [])
        if not channels:
            return f"No channels found matching '{channel_name}'."

        lines = [f"Found {len(channels)} channel(s) matching '{channel_name}':"]
        for ch in channels:
            type_label = "private" if ch["channel_type"] == "private" else "public"
            member_label = "member" if ch["is_member"] else "not a member"
            desc = ch.get("purpose") or ch.get("topic") or ""
            desc_str = f" — {desc}" if desc else ""
            lines.append(
                f"\n• #{ch['channel_name']} ({type_label}, {ch['member_count']} members, {member_label}){desc_str}"
            )
            lines.append(f"  ID: {ch['channel_id']}")

        return "\n".join(lines)

    async def _handle_find_user(self, db, user_id: str, kwargs: dict) -> str:
        from app.services.slack_search import SlackSearchService
        from app.services.slack_user import SlackUserService

        query = kwargs.get("query")
        if not query:
            return "Error: 'query' is required for find_user."

        slack_user = SlackUserService(db)
        if not await slack_user.has_oauth_token(user_id):
            return "You haven't connected your Slack account. Go to Settings > Integrations to connect."

        service = SlackSearchService(db)
        result = await service.find_users(user_id=user_id, query=query)

        if result.get("error") == "no_token":
            return "You haven't connected your Slack account. Go to Settings > Integrations to connect."
        if result.get("error"):
            return f"Error searching users: {result['error']}"

        users = result.get("users", [])
        if not users:
            return f"No users found matching '{query}'."

        lines = [f"Found {len(users)} user(s) matching '{query}':"]
        for u in users:
            title_str = f" — {u['title']}" if u.get("title") else ""
            lines.append(
                f"\n• {u['display_name']} (@{u['username']}){title_str}"
            )
            lines.append(f"  User ID: {u['user_id']}")

        return "\n".join(lines)
