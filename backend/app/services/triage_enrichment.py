"""Triage enrichment — gathers metadata for classification."""

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.repositories.triage import (
    MonitoredChannelRepository,
    TriageUserSettingsRepository,
)
from app.services.focus import FocusModeService

if TYPE_CHECKING:
    from app.services.slack import SlackService

logger = logging.getLogger(__name__)

USER_NAME_CACHE_TTL = 86400


async def resolve_user_names_batch(
    slack_service: "SlackService",
    redis_client,
    user_ids: set[str],
) -> dict[str, str]:
    """Resolve display names for multiple Slack user IDs.

    Uses same cache key format, fallback chain, and TTL as single-user resolver:
    - Cache key: slack:user_name:{user_id}
    - TTL: 24 hours
    - Fallback: real_name → profile.display_name → name → user_id

    Args:
        slack_service: SlackService instance for API calls
        redis_client: Redis client for caching
        user_ids: Set of Slack user IDs to resolve

    Returns:
        Dict mapping user_id to display name
    """
    result: dict[str, str] = {}
    uncached_ids: list[str] = []

    for user_id in user_ids:
        cache_key = f"slack:user_name:{user_id}"
        cached_name = await redis_client.get(cache_key)
        if cached_name:
            result[user_id] = cached_name
        else:
            uncached_ids.append(user_id)

    if uncached_ids:
        for user_id in uncached_ids:
            try:
                user_info = await slack_service.get_user_info(user_id)
                name = (
                    user_info.get("real_name")
                    or user_info.get("profile", {}).get("display_name")
                    or user_info.get("name")
                    or user_id
                )
                result[user_id] = name
                cache_key = f"slack:user_name:{user_id}"
                await redis_client.set(cache_key, name, ex=USER_NAME_CACHE_TTL)
            except Exception:
                result[user_id] = user_id

    return result


async def resolve_user_name(
    slack_service: "SlackService",
    redis_client,
    sender_slack_id: str,
) -> str:
    """Resolve display name for a single Slack user ID.

    Convenience wrapper that calls through batch resolver internally.

    Args:
        slack_service: SlackService instance for API calls
        redis_client: Redis client for caching
        sender_slack_id: Slack user ID to resolve

    Returns:
        Display name for the user
    """
    names = await resolve_user_names_batch(
        slack_service, redis_client, {sender_slack_id}
    )
    return names.get(sender_slack_id, sender_slack_id)


@dataclass
class EnrichedTriagePayload:
    """All metadata needed for classification (no raw text stored)."""

    user_id: str
    event_type: str  # dm | channel
    channel_id: str
    sender_slack_id: str
    message_ts: str
    thread_ts: str | None
    message_text: str  # in-memory only, discarded after classification

    # Enrichment fields
    sender_name: str = ""
    is_vip: bool = False
    focus_session_id: str | None = None
    focus_started_at: datetime | None = None
    is_in_focus: bool = False
    channel_priority: str = "medium"
    channel_name: str = ""
    slack_permalink: str | None = None
    sensitivity: str = "medium"

    # Thread context
    thread_participant_count: int = 0
    user_participated_in_thread: bool = False
    mentions_user_directly: bool = False
    thread_context_summary: str | None = None  # Summarized recent thread messages

    # DM conversation context
    dm_conversation_context: str | None = None  # Summarized recent DM messages

    # Channel-specific triage instructions
    channel_triage_instructions: str | None = None

    # User-defined classification guidance
    custom_classification_rules: str | None = None

    # Per-priority definitions (user-customizable)
    p0_definition: str | None = None
    p1_definition: str | None = None
    p2_definition: str | None = None
    p3_definition: str | None = None


def generate_slack_permalink(
    workspace_domain: str | None,
    channel_id: str,
    message_ts: str,
    thread_ts: str | None = None,
) -> str | None:
    """Generate a Slack deep link to a specific message."""
    if not workspace_domain:
        return None
    ts_clean = message_ts.replace(".", "")
    base = f"https://{workspace_domain}.slack.com/archives/{channel_id}/p{ts_clean}"
    if thread_ts and thread_ts != message_ts:
        thread_ts_clean = thread_ts.replace(".", "")
        base += f"?thread_ts={thread_ts_clean}&cid={channel_id}"
    return base


class TriageEnrichmentService:
    """Gathers all metadata needed for triage classification."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.focus_service = FocusModeService(db)
        self.settings_repo = TriageUserSettingsRepository(db)
        self.channel_repo = MonitoredChannelRepository(db)

    async def enrich(
        self,
        user_id: str,
        event_type: str,
        channel_id: str,
        sender_slack_id: str,
        message_ts: str,
        thread_ts: str | None,
        message_text: str,
    ) -> EnrichedTriagePayload:
        """Build an enriched payload with all context for classification."""
        payload = EnrichedTriagePayload(
            user_id=user_id,
            event_type=event_type,
            channel_id=channel_id,
            sender_slack_id=sender_slack_id,
            message_ts=message_ts,
            thread_ts=thread_ts,
            message_text=message_text,
        )

        # User settings
        settings = await self.settings_repo.get_by_user_id(user_id)
        if settings:
            payload.sensitivity = settings.sensitivity
            payload.custom_classification_rules = settings.custom_classification_rules
            payload.p0_definition = settings.p0_definition
            payload.p1_definition = settings.p1_definition
            payload.p2_definition = settings.p2_definition
            payload.p3_definition = settings.p3_definition

            # Auto-detect workspace domain if missing
            if not settings.slack_workspace_domain:
                try:
                    from app.services.slack import SlackService

                    slack_service = SlackService()
                    team_info = await slack_service.client.team_info()
                    if team_info.get("ok"):
                        domain = team_info["team"].get("domain")
                        if domain:
                            settings.slack_workspace_domain = domain
                            await self.db.flush()
                except Exception:
                    pass

            payload.slack_permalink = generate_slack_permalink(
                settings.slack_workspace_domain, channel_id, message_ts, thread_ts
            )

        # VIP status
        payload.is_vip = await self.focus_service.is_vip(user_id, sender_slack_id)

        # Focus session
        payload.is_in_focus = await self.focus_service.is_in_focus_mode(user_id)
        if payload.is_in_focus:
            from app.db.repositories.focus import FocusModeStateRepository

            state_repo = FocusModeStateRepository(self.db)
            state = await state_repo.get_by_user_id(user_id)
            if state and state.is_active:
                payload.focus_session_id = state.id
                payload.focus_started_at = state.started_at

        # Channel config (for channel messages)
        if event_type == "channel":
            mc = await self.channel_repo.get_by_user_and_channel(user_id, channel_id)
            if mc:
                payload.channel_priority = mc.priority
                payload.channel_name = mc.channel_name
                payload.channel_triage_instructions = mc.triage_instructions

        # Resolve sender and channel display names (best-effort)
        try:
            from app.core.redis import get_redis
            from app.services.slack import SlackService

            redis_client = await get_redis()
            slack_service = SlackService()

            # Sender name (use batch resolver for consistency)
            payload.sender_name = await resolve_user_name(
                slack_service, redis_client, sender_slack_id
            )

            # Channel name (for non-DM channels)
            if event_type == "channel" and not payload.channel_name:
                ch_cache_key = f"slack:channel_name:{channel_id}"
                cached_ch = await redis_client.get(ch_cache_key)
                if cached_ch:
                    payload.channel_name = cached_ch
                else:
                    try:
                        resp = await slack_service.client.conversations_info(
                            channel=channel_id
                        )
                        ch = resp.data.get("channel", {})
                        ch_name = ch.get("name", channel_id)
                        payload.channel_name = ch_name
                        await redis_client.set(ch_cache_key, ch_name, ex=86400)
                    except Exception:
                        pass
        except Exception:
            pass

        # Fetch thread context for thread replies
        if thread_ts and thread_ts != message_ts:
            try:
                from app.services.slack import SlackService
                from app.services.thread_context import ThreadContextService

                slack_service = SlackService()
                thread_service = ThreadContextService(slack_service.client)
                payload.thread_context_summary = (
                    await thread_service.get_thread_context(
                        channel_id=channel_id,
                        thread_ts=thread_ts,
                        max_replies=10,
                    )
                )
            except Exception:
                logger.exception(f"Failed to fetch thread context for {thread_ts}")

        # Fetch DM conversation context for direct messages
        if event_type == "dm":
            try:
                from app.services.slack import SlackService
                from app.services.thread_context import ThreadContextService

                slack_service = SlackService()
                thread_service = ThreadContextService(slack_service.client)
                payload.dm_conversation_context = (
                    await thread_service.get_dm_conversation_context(
                        channel_id=channel_id,
                        max_messages=10,
                    )
                )
            except Exception:
                logger.exception(
                    f"Failed to fetch DM conversation context for {channel_id}"
                )

        return payload
