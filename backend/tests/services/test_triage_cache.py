"""Tests for TriageCacheService."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.triage_cache import (
    CACHE_TTL,
    CHANNEL_RULES_PREFIX,
    CHANNEL_USERS_PREFIX,
    IGNORE_RULES_PREFIX,
    MONITORED_CHANNELS_KEY,
    TriageCacheService,
)


@pytest.fixture
def mock_redis():
    """Create mock Redis client.

    Uses AsyncMock for async methods but overrides pipeline() to be synchronous
    (matching the real redis-py behaviour).
    """
    r = AsyncMock()
    r.pipeline = MagicMock()  # pipeline() is sync in redis-py
    return r


@pytest.fixture
def cache_service():
    return TriageCacheService()


def _make_pipeline_mock():
    """Create a mock pipeline that behaves like redis.pipeline() (sync call, async execute)."""
    pipe = MagicMock()
    pipe.execute = AsyncMock()
    return pipe


class TestIsMonitoredChannel:
    async def test_channel_is_monitored(self, cache_service, mock_redis):
        mock_redis.sismember.return_value = True

        with patch("app.services.triage_cache.get_redis", return_value=mock_redis):
            result = await cache_service.is_monitored_channel("C12345")

        assert result is True
        mock_redis.sismember.assert_called_once_with(
            MONITORED_CHANNELS_KEY, "C12345"
        )

    async def test_channel_not_monitored(self, cache_service, mock_redis):
        mock_redis.sismember.return_value = False

        with patch("app.services.triage_cache.get_redis", return_value=mock_redis):
            result = await cache_service.is_monitored_channel("C99999")

        assert result is False


class TestAddChannel:
    async def test_add_channel(self, cache_service, mock_redis):
        with patch("app.services.triage_cache.get_redis", return_value=mock_redis):
            await cache_service.add_channel("C12345")

        mock_redis.sadd.assert_called_once_with(MONITORED_CHANNELS_KEY, "C12345")


class TestRemoveChannel:
    async def test_remove_channel(self, cache_service, mock_redis):
        with patch("app.services.triage_cache.get_redis", return_value=mock_redis):
            await cache_service.remove_channel("C12345")

        mock_redis.srem.assert_called_once_with(MONITORED_CHANNELS_KEY, "C12345")


class TestRebuildSet:
    async def test_rebuild_with_channels(self, cache_service, mock_redis):
        mock_db = AsyncMock()
        mock_pipe = _make_pipeline_mock()
        mock_redis.pipeline.return_value = mock_pipe

        with (
            patch("app.services.triage_cache.get_redis", return_value=mock_redis),
            patch(
                "app.db.repositories.triage.MonitoredChannelRepository.get_all_active_channel_ids",
                return_value=["C111", "C222", "C333"],
            ),
        ):
            await cache_service.rebuild_set(mock_db)

        mock_pipe.delete.assert_called_once_with(MONITORED_CHANNELS_KEY)
        mock_pipe.sadd.assert_called_once_with(
            MONITORED_CHANNELS_KEY, "C111", "C222", "C333"
        )
        mock_pipe.execute.assert_called_once()

    async def test_rebuild_with_no_channels(self, cache_service, mock_redis):
        mock_db = AsyncMock()
        mock_pipe = _make_pipeline_mock()
        mock_redis.pipeline.return_value = mock_pipe

        with (
            patch("app.services.triage_cache.get_redis", return_value=mock_redis),
            patch(
                "app.db.repositories.triage.MonitoredChannelRepository.get_all_active_channel_ids",
                return_value=[],
            ),
        ):
            await cache_service.rebuild_set(mock_db)

        mock_pipe.delete.assert_called_once_with(MONITORED_CHANNELS_KEY)
        mock_pipe.sadd.assert_not_called()
        mock_pipe.execute.assert_called_once()


# --- Channel Users ---


class TestGetChannelUsers:
    async def test_returns_cached_users(self, cache_service, mock_redis):
        mock_redis.exists.return_value = True
        mock_redis.smembers.return_value = {"U111", "U222"}

        with patch("app.services.triage_cache.get_redis", return_value=mock_redis):
            result = await cache_service.get_channel_users("C100")

        assert result == {"U111", "U222"}
        expected_key = f"{CHANNEL_USERS_PREFIX}C100"
        mock_redis.exists.assert_called_once_with(expected_key)
        mock_redis.smembers.assert_called_once_with(expected_key)

    async def test_returns_none_when_not_cached(self, cache_service, mock_redis):
        mock_redis.exists.return_value = False

        with patch("app.services.triage_cache.get_redis", return_value=mock_redis):
            result = await cache_service.get_channel_users("C100")

        assert result is None
        mock_redis.smembers.assert_not_called()

    async def test_decodes_bytes_members(self, cache_service, mock_redis):
        mock_redis.exists.return_value = True
        mock_redis.smembers.return_value = {b"U111", b"U222"}

        with patch("app.services.triage_cache.get_redis", return_value=mock_redis):
            result = await cache_service.get_channel_users("C100")

        assert result == {"U111", "U222"}


class TestSetChannelUsers:
    async def test_sets_users_with_ttl(self, cache_service, mock_redis):
        mock_pipe = _make_pipeline_mock()
        mock_redis.pipeline.return_value = mock_pipe

        with patch("app.services.triage_cache.get_redis", return_value=mock_redis):
            await cache_service.set_channel_users("C100", {"U111", "U222"})

        expected_key = f"{CHANNEL_USERS_PREFIX}C100"
        mock_pipe.delete.assert_called_once_with(expected_key)
        mock_pipe.sadd.assert_called_once()
        # Verify the key and members (order-independent)
        args = mock_pipe.sadd.call_args[0]
        assert args[0] == expected_key
        assert set(args[1:]) == {"U111", "U222"}
        mock_pipe.expire.assert_called_once_with(expected_key, CACHE_TTL)
        mock_pipe.execute.assert_called_once()

    async def test_sets_empty_users(self, cache_service, mock_redis):
        mock_pipe = _make_pipeline_mock()
        mock_redis.pipeline.return_value = mock_pipe

        with patch("app.services.triage_cache.get_redis", return_value=mock_redis):
            await cache_service.set_channel_users("C100", set())

        expected_key = f"{CHANNEL_USERS_PREFIX}C100"
        mock_pipe.delete.assert_called_once_with(expected_key)
        mock_pipe.sadd.assert_not_called()
        mock_pipe.expire.assert_called_once_with(expected_key, CACHE_TTL)
        mock_pipe.execute.assert_called_once()


class TestInvalidateChannelUsers:
    async def test_deletes_key(self, cache_service, mock_redis):
        with patch("app.services.triage_cache.get_redis", return_value=mock_redis):
            await cache_service.invalidate_channel_users("C100")

        expected_key = f"{CHANNEL_USERS_PREFIX}C100"
        mock_redis.delete.assert_called_once_with(expected_key)


# --- Ignore Rules ---


class TestIsSenderIgnored:
    async def test_returns_true_when_sender_ignored(self, cache_service, mock_redis):
        mock_redis.exists.return_value = True
        mock_redis.sismember.return_value = True

        with patch("app.services.triage_cache.get_redis", return_value=mock_redis):
            result = await cache_service.is_sender_ignored("U001", "C100", "U999")

        assert result is True
        expected_key = f"{IGNORE_RULES_PREFIX}U001:C100"
        mock_redis.exists.assert_called_once_with(expected_key)
        mock_redis.sismember.assert_called_once_with(expected_key, "U999")

    async def test_returns_false_when_sender_not_ignored(
        self, cache_service, mock_redis
    ):
        mock_redis.exists.return_value = True
        mock_redis.sismember.return_value = False

        with patch("app.services.triage_cache.get_redis", return_value=mock_redis):
            result = await cache_service.is_sender_ignored("U001", "C100", "U999")

        assert result is False

    async def test_returns_none_when_not_cached(self, cache_service, mock_redis):
        mock_redis.exists.return_value = False

        with patch("app.services.triage_cache.get_redis", return_value=mock_redis):
            result = await cache_service.is_sender_ignored("U001", "C100", "U999")

        assert result is None
        mock_redis.sismember.assert_not_called()


class TestSetIgnoreRules:
    async def test_sets_ignored_ids_with_ttl(self, cache_service, mock_redis):
        mock_pipe = _make_pipeline_mock()
        mock_redis.pipeline.return_value = mock_pipe

        with patch("app.services.triage_cache.get_redis", return_value=mock_redis):
            await cache_service.set_ignore_rules("U001", "C100", {"U999", "B001"})

        expected_key = f"{IGNORE_RULES_PREFIX}U001:C100"
        mock_pipe.delete.assert_called_once_with(expected_key)
        args = mock_pipe.sadd.call_args[0]
        assert args[0] == expected_key
        assert set(args[1:]) == {"U999", "B001"}
        mock_pipe.expire.assert_called_once_with(expected_key, CACHE_TTL)
        mock_pipe.execute.assert_called_once()

    async def test_uses_empty_marker_for_empty_set(self, cache_service, mock_redis):
        mock_pipe = _make_pipeline_mock()
        mock_redis.pipeline.return_value = mock_pipe

        with patch("app.services.triage_cache.get_redis", return_value=mock_redis):
            await cache_service.set_ignore_rules("U001", "C100", set())

        expected_key = f"{IGNORE_RULES_PREFIX}U001:C100"
        mock_pipe.delete.assert_called_once_with(expected_key)
        mock_pipe.sadd.assert_called_once_with(expected_key, "__EMPTY__")
        mock_pipe.expire.assert_called_once_with(expected_key, CACHE_TTL)
        mock_pipe.execute.assert_called_once()


class TestInvalidateIgnoreRules:
    async def test_deletes_key(self, cache_service, mock_redis):
        with patch("app.services.triage_cache.get_redis", return_value=mock_redis):
            await cache_service.invalidate_ignore_rules("U001", "C100")

        expected_key = f"{IGNORE_RULES_PREFIX}U001:C100"
        mock_redis.delete.assert_called_once_with(expected_key)


# --- Channel Rules ---


class TestGetChannelRules:
    async def test_returns_cached_rules(self, cache_service, mock_redis):
        mock_redis.exists.return_value = True
        mock_redis.hgetall.return_value = {"priority": "high", "keywords": "urgent"}

        with patch("app.services.triage_cache.get_redis", return_value=mock_redis):
            result = await cache_service.get_channel_rules("U001", "C100")

        assert result == {"priority": "high", "keywords": "urgent"}
        expected_key = f"{CHANNEL_RULES_PREFIX}U001:C100"
        mock_redis.exists.assert_called_once_with(expected_key)
        mock_redis.hgetall.assert_called_once_with(expected_key)

    async def test_returns_none_when_not_cached(self, cache_service, mock_redis):
        mock_redis.exists.return_value = False

        with patch("app.services.triage_cache.get_redis", return_value=mock_redis):
            result = await cache_service.get_channel_rules("U001", "C100")

        assert result is None
        mock_redis.hgetall.assert_not_called()

    async def test_decodes_bytes_keys_and_values(self, cache_service, mock_redis):
        mock_redis.exists.return_value = True
        mock_redis.hgetall.return_value = {b"priority": b"high", b"keywords": b"urgent"}

        with patch("app.services.triage_cache.get_redis", return_value=mock_redis):
            result = await cache_service.get_channel_rules("U001", "C100")

        assert result == {"priority": "high", "keywords": "urgent"}


class TestSetChannelRules:
    async def test_sets_rules_with_ttl(self, cache_service, mock_redis):
        mock_pipe = _make_pipeline_mock()
        mock_redis.pipeline.return_value = mock_pipe
        rules = {"priority": "high", "keywords": "urgent"}

        with patch("app.services.triage_cache.get_redis", return_value=mock_redis):
            await cache_service.set_channel_rules("U001", "C100", rules)

        expected_key = f"{CHANNEL_RULES_PREFIX}U001:C100"
        mock_pipe.delete.assert_called_once_with(expected_key)
        mock_pipe.hset.assert_called_once_with(expected_key, mapping=rules)
        mock_pipe.expire.assert_called_once_with(expected_key, CACHE_TTL)
        mock_pipe.execute.assert_called_once()

    async def test_sets_empty_rules(self, cache_service, mock_redis):
        mock_pipe = _make_pipeline_mock()
        mock_redis.pipeline.return_value = mock_pipe

        with patch("app.services.triage_cache.get_redis", return_value=mock_redis):
            await cache_service.set_channel_rules("U001", "C100", {})

        expected_key = f"{CHANNEL_RULES_PREFIX}U001:C100"
        mock_pipe.delete.assert_called_once_with(expected_key)
        mock_pipe.hset.assert_not_called()
        mock_pipe.expire.assert_called_once_with(expected_key, CACHE_TTL)
        mock_pipe.execute.assert_called_once()


class TestInvalidateChannelRules:
    async def test_deletes_key(self, cache_service, mock_redis):
        with patch("app.services.triage_cache.get_redis", return_value=mock_redis):
            await cache_service.invalidate_channel_rules("U001", "C100")

        expected_key = f"{CHANNEL_RULES_PREFIX}U001:C100"
        mock_redis.delete.assert_called_once_with(expected_key)
