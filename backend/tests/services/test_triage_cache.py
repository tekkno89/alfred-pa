"""Tests for TriageCacheService."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.triage_cache import TriageCacheService, MONITORED_CHANNELS_KEY


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
