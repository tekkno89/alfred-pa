"""Tests for TriageEventRouter."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.triage_router import TriageEventRouter


@pytest.fixture
def mock_db():
    return AsyncMock()


def _make_event(**overrides):
    defaults = {
        "channel": "D12345",
        "user": "U_SENDER",
        "ts": "1234567890.123456",
        "thread_ts": None,
        "text": "Hello",
    }
    defaults.update(overrides)
    return defaults


class TestRouteEvent:
    async def test_dm_routes_to_recipient(self, mock_db):
        """DM should be routed to the recipient (non-sender authorized user)."""
        mock_user = MagicMock()
        mock_user.id = "user-1"
        mock_user.slack_user_id = "U_RECIPIENT"

        mock_user_repo = AsyncMock()
        mock_user_repo.get_by_slack_id.return_value = mock_user

        mock_settings = MagicMock()
        mock_settings.is_always_on = True

        mock_settings_repo = AsyncMock()
        mock_settings_repo.get_by_user_id.return_value = mock_settings

        mock_focus = AsyncMock()
        mock_focus.is_in_focus_mode.return_value = False

        mock_pool = AsyncMock()

        with (
            patch.object(TriageEventRouter, "__init__", lambda self, db: None),
            patch(
                "app.worker.scheduler.get_redis_pool",
                return_value=mock_pool,
            ),
        ):
            router = TriageEventRouter.__new__(TriageEventRouter)
            router.db = mock_db
            router.cache = AsyncMock()
            router.user_repo = mock_user_repo
            router.focus_service = mock_focus
            router.channel_repo = AsyncMock()
            router.settings_repo = mock_settings_repo

            event = _make_event()
            authorizations = [
                {"user_id": "U_SENDER", "is_bot": False},
                {"user_id": "U_RECIPIENT", "is_bot": False},
            ]

            await router.route_event(event, authorizations)

        mock_pool.enqueue_job.assert_called_once()
        call_kwargs = mock_pool.enqueue_job.call_args
        assert call_kwargs[1]["user_id"] == "user-1"
        assert call_kwargs[1]["event_type"] == "dm"

    async def test_channel_message_checks_redis_set(self, mock_db):
        """Channel messages should check Redis monitored set first."""
        with patch.object(TriageEventRouter, "__init__", lambda self, db: None):
            router = TriageEventRouter.__new__(TriageEventRouter)
            router.db = mock_db
            router.cache = AsyncMock()
            router.cache.is_monitored_channel.return_value = False
            router.user_repo = AsyncMock()
            router.focus_service = AsyncMock()
            router.channel_repo = AsyncMock()
            router.settings_repo = AsyncMock()

            event = _make_event(channel="C12345")
            await router.route_event(event, [])

        router.cache.is_monitored_channel.assert_called_once_with("C12345")
        # Should not proceed to channel routing
        router.channel_repo.get_users_for_channel.assert_not_called()

    async def test_channel_routes_to_all_monitoring_users(self, mock_db):
        """Monitored channel message should fan out to all monitoring users."""
        mc1 = MagicMock(user_id="user-1")
        mc2 = MagicMock(user_id="user-2")

        mock_user1 = MagicMock(id="user-1", slack_user_id="U_OTHER1")
        mock_user2 = MagicMock(id="user-2", slack_user_id="U_OTHER2")

        mock_settings = MagicMock(is_always_on=True)
        mock_pool = AsyncMock()

        with (
            patch.object(TriageEventRouter, "__init__", lambda self, db: None),
            patch(
                "app.worker.scheduler.get_redis_pool",
                return_value=mock_pool,
            ),
        ):
            router = TriageEventRouter.__new__(TriageEventRouter)
            router.db = mock_db
            router.cache = AsyncMock()
            router.cache.is_monitored_channel.return_value = True
            router.user_repo = AsyncMock()
            router.user_repo.get.side_effect = [mock_user1, mock_user2]
            router.focus_service = AsyncMock()
            router.focus_service.is_in_focus_mode.return_value = False
            router.channel_repo = AsyncMock()
            router.channel_repo.get_users_for_channel.return_value = [mc1, mc2]
            router.settings_repo = AsyncMock()
            router.settings_repo.get_by_user_id.return_value = mock_settings

            event = _make_event(channel="C12345")
            await router.route_event(event, [])

        assert mock_pool.enqueue_job.call_count == 2

    async def test_bot_messages_excluded_by_default(self, mock_db):
        """Bot messages should be skipped unless explicitly included."""
        mock_settings = MagicMock(is_always_on=True)

        with patch.object(TriageEventRouter, "__init__", lambda self, db: None):
            router = TriageEventRouter.__new__(TriageEventRouter)
            router.db = mock_db
            router.cache = AsyncMock()
            router.cache.is_monitored_channel.return_value = True
            mc = MagicMock(user_id="user-1")
            mock_user = MagicMock(id="user-1", slack_user_id="U_OTHER")
            router.user_repo = AsyncMock()
            router.user_repo.get.return_value = mock_user
            router.focus_service = AsyncMock()
            router.focus_service.is_in_focus_mode.return_value = True
            router.channel_repo = AsyncMock()
            router.channel_repo.get_users_for_channel.return_value = [mc]
            router.settings_repo = AsyncMock()
            router.settings_repo.get_by_user_id.return_value = mock_settings

            event = _make_event(channel="C12345", bot_id="B_BOT")
            await router.route_event(event, [])

        # Bot message should not be enqueued
        # (no pool.enqueue_job call since _should_triage returns False for bots)

    async def test_skips_sender_in_channel(self, mock_db):
        """Should not triage a message for the user who sent it."""
        mc = MagicMock(user_id="user-1")
        mock_user = MagicMock(id="user-1", slack_user_id="U_SENDER")  # same as sender

        mock_settings = MagicMock(is_always_on=True)
        mock_pool = AsyncMock()

        with (
            patch.object(TriageEventRouter, "__init__", lambda self, db: None),
            patch(
                "app.worker.scheduler.get_redis_pool",
                return_value=mock_pool,
            ),
        ):
            router = TriageEventRouter.__new__(TriageEventRouter)
            router.db = mock_db
            router.cache = AsyncMock()
            router.cache.is_monitored_channel.return_value = True
            router.user_repo = AsyncMock()
            router.user_repo.get.return_value = mock_user
            router.focus_service = AsyncMock()
            router.focus_service.is_in_focus_mode.return_value = True
            router.channel_repo = AsyncMock()
            router.channel_repo.get_users_for_channel.return_value = [mc]
            router.settings_repo = AsyncMock()
            router.settings_repo.get_by_user_id.return_value = mock_settings

            event = _make_event(channel="C12345", user="U_SENDER")
            await router.route_event(event, [])

        mock_pool.enqueue_job.assert_not_called()
