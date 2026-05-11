"""Unit tests for SlackMessageCache service."""

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.slack_message_cache import (
    MESSAGE_TTL_DAYS,
    SlackMessageCacheService,
)


@pytest.fixture
def mock_db():
    return AsyncMock(spec=AsyncSession)


@pytest.fixture
def mock_slack_service():
    service = AsyncMock()
    return service


@pytest.fixture
def cache_service(mock_db):
    return SlackMessageCacheService(mock_db)


class TestGetMessage:
    async def test_get_message_found(self, cache_service, mock_db):
        mock_result = MagicMock()
        mock_row = MagicMock()
        mock_row.text = "Test message content"
        mock_result.scalar_one_or_none.return_value = mock_row
        mock_db.execute.return_value = mock_result

        result = await cache_service.get_message(
            "T12345", "C67890", "1234567890.123456"
        )

        assert result == "Test message content"

    async def test_get_message_not_found(self, cache_service, mock_db):
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        result = await cache_service.get_message(
            "T12345", "C67890", "9999999999.999999"
        )

        assert result is None


class TestGetThreadMessages:
    async def test_get_thread_messages_found(self, cache_service, mock_db):
        mock_result = MagicMock()
        mock_rows = [
            MagicMock(
                sender_slack_id="U111",
                text="First message",
                message_ts="1234567890.111111",
            ),
            MagicMock(
                sender_slack_id="U222",
                text="Reply message",
                message_ts="1234567890.222222",
            ),
        ]
        mock_result.fetchall.return_value = mock_rows
        mock_db.execute.return_value = mock_result

        result = await cache_service.get_thread_messages(
            "T12345", "C67890", "1234567890.111111"
        )

        assert len(result) == 2
        assert result[0] == ("U111", "First message", "1234567890.111111")
        assert result[1] == ("U222", "Reply message", "1234567890.222222")

    async def test_get_thread_messages_empty(self, cache_service, mock_db):
        mock_result = MagicMock()
        mock_result.fetchall.return_value = []
        mock_db.execute.return_value = mock_result

        result = await cache_service.get_thread_messages(
            "T12345", "C67890", "1234567890.111111"
        )

        assert result == []


class TestShouldCache:
    async def test_should_cache_public_non_sensitive(
        self, cache_service, mock_db
    ):
        mock_channel = MagicMock()
        mock_channel.channel_type = "public"
        mock_channel.sensitive = False

        with patch(
            "app.services.slack_message_cache.MonitoredChannelRepository"
        ) as mock_repo_class:
            mock_repo = MagicMock()
            mock_repo.get_by_user_and_channel = AsyncMock(
                return_value=mock_channel
            )
            mock_repo_class.return_value = mock_repo

            result = await cache_service.should_cache("user123", "C67890")

        assert result is True

    async def test_should_not_cache_public_sensitive(
        self, cache_service, mock_db
    ):
        mock_channel = MagicMock()
        mock_channel.channel_type = "public"
        mock_channel.sensitive = True

        with patch(
            "app.services.slack_message_cache.MonitoredChannelRepository"
        ) as mock_repo_class:
            mock_repo = MagicMock()
            mock_repo.get_by_user_and_channel = AsyncMock(
                return_value=mock_channel
            )
            mock_repo_class.return_value = mock_repo

            result = await cache_service.should_cache("user123", "C67890")

        assert result is False

    async def test_should_not_cache_private_channel(
        self, cache_service, mock_db
    ):
        mock_channel = MagicMock()
        mock_channel.channel_type = "private"
        mock_channel.sensitive = False

        with patch(
            "app.services.slack_message_cache.MonitoredChannelRepository"
        ) as mock_repo_class:
            mock_repo = MagicMock()
            mock_repo.get_by_user_and_channel = AsyncMock(
                return_value=mock_channel
            )
            mock_repo_class.return_value = mock_repo

            result = await cache_service.should_cache("user123", "C67890")

        assert result is False

    async def test_should_not_cache_channel_not_monitored(
        self, cache_service, mock_db
    ):
        with patch(
            "app.services.slack_message_cache.MonitoredChannelRepository"
        ) as mock_repo_class:
            mock_repo = MagicMock()
            mock_repo.get_by_user_and_channel = AsyncMock(return_value=None)
            mock_repo_class.return_value = mock_repo

            result = await cache_service.should_cache("user123", "C67890")

        assert result is False


class TestFetchAndCache:
    async def test_fetch_and_cache_new_message(
        self, cache_service, mock_db, mock_slack_service
    ):
        ts = "1234567890.123456"
        mock_slack_service.get_message.return_value = {
            "text": "Test message",
            "user": "U12345",
            "bot_id": None,
            "thread_ts": "1234567890.000000",
            "ts": ts,
        }

        with patch.object(
            cache_service, "should_cache", return_value=True
        ) as mock_should:
            result = await cache_service.fetch_and_cache(
                "T12345", "C67890", ts, mock_slack_service, "user123"
            )

        assert result == "Test message"
        mock_slack_service.get_message.assert_called_once_with(
            "C67890", ts
        )
        mock_db.add.assert_called_once()
        mock_db.commit.assert_called_once()

    async def test_fetch_and_cache_should_not_cache(
        self, cache_service, mock_db, mock_slack_service
    ):
        ts = "1234567890.123456"
        mock_slack_service.get_message.return_value = {
            "text": "Test message",
            "user": "U12345",
            "bot_id": None,
            "thread_ts": None,
            "ts": ts,
        }

        with patch.object(
            cache_service, "should_cache", return_value=False
        ) as mock_should:
            result = await cache_service.fetch_and_cache(
                "T12345", "C67890", ts, mock_slack_service, "user123"
            )

        assert result == "Test message"
        mock_slack_service.get_message.assert_called_once()
        mock_db.add.assert_not_called()

    async def test_fetch_and_cache_message_not_found(
        self, cache_service, mock_db, mock_slack_service
    ):
        ts = "1234567890.123456"
        mock_slack_service.get_message.return_value = None

        with patch.object(
            cache_service, "should_cache", return_value=True
        ) as mock_should:
            result = await cache_service.fetch_and_cache(
                "T12345", "C67890", ts, mock_slack_service, "user123"
            )

        assert result is None
        mock_db.add.assert_not_called()

    async def test_fetch_and_cache_bot_message(
        self, cache_service, mock_db, mock_slack_service
    ):
        ts = "1234567890.123456"
        mock_slack_service.get_message.return_value = {
            "text": "Bot message",
            "bot_id": "B12345",
            "thread_ts": None,
            "ts": ts,
        }

        with patch.object(
            cache_service, "should_cache", return_value=True
        ) as mock_should:
            result = await cache_service.fetch_and_cache(
                "T12345", "C67890", ts, mock_slack_service, "user123"
            )

        assert result == "Bot message"
        mock_db.add.assert_called_once()
        added_msg = mock_db.add.call_args[0][0]
        assert added_msg.is_bot is True


class TestCacheThread:
    async def test_cache_thread_success(
        self, cache_service, mock_db, mock_slack_service
    ):
        thread_ts = "1234567890.000000"
        mock_slack_service.get_thread_messages.return_value = [
            {
                "text": "Thread parent",
                "user": "U111",
                "bot_id": None,
                "thread_ts": thread_ts,
                "ts": thread_ts,
            },
            {
                "text": "Thread reply",
                "user": "U222",
                "bot_id": None,
                "thread_ts": thread_ts,
                "ts": "1234567890.111111",
            },
        ]

        with patch.object(
            cache_service, "should_cache", return_value=True
        ) as mock_should:
            result = await cache_service.cache_thread(
                "T12345", "C67890", thread_ts, mock_slack_service, "user123"
            )

        assert len(result) == 2
        assert result[0] == ("U111", "Thread parent", thread_ts)
        assert result[1] == ("U222", "Thread reply", "1234567890.111111")
        assert mock_db.add.call_count == 2

    async def test_cache_thread_should_not_cache(
        self, cache_service, mock_db, mock_slack_service
    ):
        thread_ts = "1234567890.000000"
        mock_slack_service.get_thread_messages.return_value = [
            {
                "text": "Message",
                "user": "U111",
                "bot_id": None,
                "thread_ts": thread_ts,
                "ts": thread_ts,
            }
        ]

        with patch.object(
            cache_service, "should_cache", return_value=False
        ) as mock_should:
            result = await cache_service.cache_thread(
                "T12345", "C67890", thread_ts, mock_slack_service, "user123"
            )

        assert len(result) == 1
        mock_db.add.assert_not_called()


class TestCleanupExpired:
    async def test_cleanup_expired_deletes_old_messages(
        self, cache_service, mock_db
    ):
        mock_result = MagicMock()
        mock_result.rowcount = 5
        mock_db.execute.return_value = mock_result

        deleted_count = await cache_service.cleanup_expired()

        assert deleted_count == 5
        mock_db.commit.assert_called_once()

    async def test_cleanup_expired_no_old_messages(
        self, cache_service, mock_db
    ):
        mock_result = MagicMock()
        mock_result.rowcount = 0
        mock_db.execute.return_value = mock_result

        deleted_count = await cache_service.cleanup_expired()

        assert deleted_count == 0


class TestTTLConstant:
    def test_ttl_is_7_days(self):
        assert MESSAGE_TTL_DAYS == 7
