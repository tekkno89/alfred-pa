"""Triage pre-filter: deterministic message scoping and user fan-out.

Stage 2 of the agent-driven triage pipeline. No LLM calls.
Determines which Alfred users should receive a message for classification.
"""

import logging
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.repositories import UserRepository
from app.db.repositories.triage import (
    ChannelSourceRuleRepository,
    MonitoredChannelRepository,
    TriageUserSettingsRepository,
)
from app.services.focus import FocusModeService
from app.services.triage_cache import TriageCacheService

logger = logging.getLogger(__name__)


class TriagePrefilter:
    """Determines which users should receive a message for triage classification.

    Uses Redis-cached data for fast lookups:
    - Monitored channels SET
    - Channel users SET per channel
    - Ignore rules SET per user+channel

    Falls back to DB queries on cache miss, then populates cache.
    """

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.cache = TriageCacheService()
        self.user_repo = UserRepository(db)
        self.channel_repo = MonitoredChannelRepository(db)
        self.settings_repo = TriageUserSettingsRepository(db)
        self.focus_service = FocusModeService(db)
        self.source_rule_repo = ChannelSourceRuleRepository(db)

    async def get_applicable_users(
        self,
        channel_id: str,
        channel_type: str,
        sender_slack_id: str,
        authorizations: list[dict[str, Any]] | None = None,
    ) -> list[str]:
        """Get list of user_ids that should receive this message for triage.

        Args:
            channel_id: Slack channel ID
            channel_type: "channel", "group", "im", "mpim"
            sender_slack_id: Slack user ID of the sender
            authorizations: Slack event authorizations (for DMs)

        Returns:
            List of Alfred user IDs that should receive this message
        """
        if channel_type in ("im", "mpim"):
            return await self._get_dm_applicable_users(
                channel_id, sender_slack_id, authorizations or []
            )

        if not await self.cache.is_monitored_channel(channel_id):
            return []

        return await self._get_channel_applicable_users(
            channel_id, sender_slack_id
        )

    async def _get_channel_applicable_users(
        self,
        channel_id: str,
        sender_slack_id: str,
    ) -> list[str]:
        """Get applicable users for a channel message."""
        user_ids = await self.cache.get_channel_users(channel_id)
        if user_ids is None:
            monitored = await self.channel_repo.get_users_for_channel(channel_id)
            user_ids = {str(mc.user_id) for mc in monitored if mc.is_active}
            await self.cache.set_channel_users(channel_id, user_ids)

        applicable = []
        for user_id in user_ids:
            user_slack_id = await self._get_user_slack_id(user_id)
            if user_slack_id == sender_slack_id:
                continue

            ignored = await self.cache.is_sender_ignored(
                user_id, channel_id, sender_slack_id
            )
            if ignored is None:
                ignore_rules = await self.source_rule_repo.get_ignore_rules(
                    user_id, channel_id
                )
                ignored_ids = {r.slack_entity_id for r in ignore_rules}
                await self.cache.set_ignore_rules(user_id, channel_id, ignored_ids)
                ignored = sender_slack_id in ignored_ids
            if ignored:
                continue

            if not await self._should_triage(user_id):
                continue

            applicable.append(user_id)

        return applicable

    async def _get_dm_applicable_users(
        self,
        channel_id: str,
        sender_slack_id: str,
        authorizations: list[dict[str, Any]],
    ) -> list[str]:
        """Get applicable users for a DM."""
        applicable = []
        for auth in authorizations:
            auth_slack_id = auth.get("user_id")
            if not auth_slack_id or auth_slack_id == sender_slack_id:
                continue
            user = await self.user_repo.get_by_slack_id(auth_slack_id)
            if not user:
                continue
            if not await self._should_triage(str(user.id)):
                continue
            applicable.append(str(user.id))
        return applicable

    async def _should_triage(self, user_id: str) -> bool:
        """Check if user has triage enabled (always-on or focus mode)."""
        settings = await self.settings_repo.get_by_user_id(user_id)
        if not settings:
            return False
        if settings.is_always_on:
            return True
        return await self.focus_service.is_in_focus_mode(user_id)

    async def _get_user_slack_id(self, user_id: str) -> str | None:
        """Get a user's Slack ID from their Alfred user ID."""
        user = await self.user_repo.get(user_id)
        return user.slack_user_id if user else None
