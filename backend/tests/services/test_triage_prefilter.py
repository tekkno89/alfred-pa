"""Tests for triage pre-filter worker."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from app.services.triage_prefilter import TriagePrefilter


@pytest.fixture
def mock_db():
    return AsyncMock()


@pytest.fixture
def prefilter(mock_db):
    pf = TriagePrefilter(mock_db)
    pf.cache = AsyncMock()
    pf.user_repo = AsyncMock()
    pf.channel_repo = AsyncMock()
    pf.settings_repo = AsyncMock()
    pf.focus_service = AsyncMock()
    pf.source_rule_repo = AsyncMock()
    return pf


class TestChannelScopeCheck:
    @pytest.mark.asyncio
    async def test_unmonitored_channel_returns_empty(self, prefilter):
        prefilter.cache.is_monitored_channel = AsyncMock(return_value=False)
        result = await prefilter.get_applicable_users(
            channel_id="C_UNMONITORED",
            channel_type="channel",
            sender_slack_id="U_SENDER",
        )
        assert result == []

    @pytest.mark.asyncio
    async def test_monitored_channel_with_user(self, prefilter):
        prefilter.cache.is_monitored_channel = AsyncMock(return_value=True)
        prefilter.cache.get_channel_users = AsyncMock(return_value={"user1"})
        prefilter.cache.is_sender_ignored = AsyncMock(return_value=False)

        mock_user = MagicMock()
        mock_user.slack_user_id = "U_OTHER"
        prefilter.user_repo.get = AsyncMock(return_value=mock_user)

        mock_settings = MagicMock()
        mock_settings.is_always_on = True
        prefilter.settings_repo.get_by_user_id = AsyncMock(return_value=mock_settings)

        result = await prefilter.get_applicable_users(
            channel_id="C_MONITORED",
            channel_type="channel",
            sender_slack_id="U_SENDER",
        )
        assert result == ["user1"]


class TestSenderFiltering:
    @pytest.mark.asyncio
    async def test_sender_is_user_skipped(self, prefilter):
        prefilter.cache.is_monitored_channel = AsyncMock(return_value=True)
        prefilter.cache.get_channel_users = AsyncMock(return_value={"user1"})

        mock_user = MagicMock()
        mock_user.slack_user_id = "U_SENDER"  # Same as sender
        prefilter.user_repo.get = AsyncMock(return_value=mock_user)

        result = await prefilter.get_applicable_users(
            channel_id="C123",
            channel_type="channel",
            sender_slack_id="U_SENDER",
        )
        assert result == []

    @pytest.mark.asyncio
    async def test_ignored_sender_skipped(self, prefilter):
        prefilter.cache.is_monitored_channel = AsyncMock(return_value=True)
        prefilter.cache.get_channel_users = AsyncMock(return_value={"user1"})
        prefilter.cache.is_sender_ignored = AsyncMock(return_value=True)

        mock_user = MagicMock()
        mock_user.slack_user_id = "U_OTHER"
        prefilter.user_repo.get = AsyncMock(return_value=mock_user)

        mock_settings = MagicMock()
        mock_settings.is_always_on = True
        prefilter.settings_repo.get_by_user_id = AsyncMock(return_value=mock_settings)

        result = await prefilter.get_applicable_users(
            channel_id="C123",
            channel_type="channel",
            sender_slack_id="U_IGNORED",
        )
        assert result == []

    @pytest.mark.asyncio
    async def test_triage_not_enabled_skipped(self, prefilter):
        prefilter.cache.is_monitored_channel = AsyncMock(return_value=True)
        prefilter.cache.get_channel_users = AsyncMock(return_value={"user1"})
        prefilter.cache.is_sender_ignored = AsyncMock(return_value=False)

        mock_user = MagicMock()
        mock_user.slack_user_id = "U_OTHER"
        prefilter.user_repo.get = AsyncMock(return_value=mock_user)

        mock_settings = MagicMock()
        mock_settings.is_always_on = False
        prefilter.settings_repo.get_by_user_id = AsyncMock(return_value=mock_settings)
        prefilter.focus_service.is_in_focus_mode = AsyncMock(return_value=False)

        result = await prefilter.get_applicable_users(
            channel_id="C123",
            channel_type="channel",
            sender_slack_id="U_SENDER",
        )
        assert result == []


class TestCacheMissDBFallback:
    @pytest.mark.asyncio
    async def test_channel_users_cache_miss_queries_db(self, prefilter):
        prefilter.cache.is_monitored_channel = AsyncMock(return_value=True)
        prefilter.cache.get_channel_users = AsyncMock(return_value=None)  # Cache miss
        prefilter.cache.is_sender_ignored = AsyncMock(return_value=False)

        mc = MagicMock()
        mc.user_id = "user1"
        mc.is_active = True
        prefilter.channel_repo.get_users_for_channel = AsyncMock(return_value=[mc])

        mock_user = MagicMock()
        mock_user.slack_user_id = "U_OTHER"
        prefilter.user_repo.get = AsyncMock(return_value=mock_user)

        mock_settings = MagicMock()
        mock_settings.is_always_on = True
        prefilter.settings_repo.get_by_user_id = AsyncMock(return_value=mock_settings)

        result = await prefilter.get_applicable_users(
            channel_id="C123",
            channel_type="channel",
            sender_slack_id="U_SENDER",
        )

        assert result == ["user1"]
        prefilter.channel_repo.get_users_for_channel.assert_called_once()
        prefilter.cache.set_channel_users.assert_called_once()


class TestDMHandling:
    @pytest.mark.asyncio
    async def test_dm_skips_channel_check(self, prefilter):
        prefilter.cache.is_monitored_channel = AsyncMock(return_value=False)

        mock_user = MagicMock()
        mock_user.id = "user1"
        prefilter.user_repo.get_by_slack_id = AsyncMock(return_value=mock_user)

        mock_settings = MagicMock()
        mock_settings.is_always_on = True
        prefilter.settings_repo.get_by_user_id = AsyncMock(return_value=mock_settings)

        result = await prefilter.get_applicable_users(
            channel_id="D_DM",
            channel_type="im",
            sender_slack_id="U_SENDER",
            authorizations=[{"user_id": "U_RECIPIENT"}],
        )

        assert result == ["user1"]
        prefilter.cache.is_monitored_channel.assert_not_called()

    @pytest.mark.asyncio
    async def test_dm_sender_not_included(self, prefilter):
        result = await prefilter.get_applicable_users(
            channel_id="D_DM",
            channel_type="im",
            sender_slack_id="U_SENDER",
            authorizations=[{"user_id": "U_SENDER"}],
        )
        assert result == []
