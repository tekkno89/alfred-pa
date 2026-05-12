"""Tests for worker tasks."""

import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch, MagicMock


class TestCleanupSlackMessageCache:
    """Tests for cleanup_slack_message_cache task."""

    async def test_cleanup_deletes_old_rows(self):
        """Old cache rows beyond retention should be deleted."""
        from app.worker.tasks import cleanup_slack_message_cache

        mock_settings = MagicMock()
        mock_settings.slack_message_cache_retention_days = 7

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.rowcount = 100
        mock_session.execute.return_value = mock_result

        with patch("app.worker.tasks.get_db_session") as mock_ctx:
            mock_ctx.return_value.__aenter__.return_value = mock_session
            with patch("app.worker.tasks.get_settings", return_value=mock_settings):
                # Return 100, then 0 to exit the loop
                mock_session.execute.side_effect = [
                    MagicMock(rowcount=100),
                    MagicMock(rowcount=0),
                ]
                result = await cleanup_slack_message_cache({})

        assert result["status"] == "complete"
        assert result["deleted_count"] == 100
        assert mock_session.execute.call_count == 2

    async def test_cleanup_respects_retention_config(self):
        """Retention period should be configurable."""
        from app.worker.tasks import cleanup_slack_message_cache

        mock_settings = MagicMock()
        mock_settings.slack_message_cache_retention_days = 3

        mock_session = AsyncMock()
        mock_session.execute.side_effect = [
            MagicMock(rowcount=50),
            MagicMock(rowcount=0),
        ]

        with patch("app.worker.tasks.get_db_session") as mock_ctx:
            mock_ctx.return_value.__aenter__.return_value = mock_session
            with patch("app.worker.tasks.get_settings", return_value=mock_settings):
                result = await cleanup_slack_message_cache({})

        assert result["deleted_count"] == 50

    async def test_cleanup_handles_empty_result(self):
        """No old rows should return zero count."""
        from app.worker.tasks import cleanup_slack_message_cache

        mock_settings = MagicMock()
        mock_settings.slack_message_cache_retention_days = 7

        mock_session = AsyncMock()
        mock_session.execute.side_effect = [
            MagicMock(rowcount=0),
        ]

        with patch("app.worker.tasks.get_db_session") as mock_ctx:
            mock_ctx.return_value.__aenter__.return_value = mock_session
            with patch("app.worker.tasks.get_settings", return_value=mock_settings):
                result = await cleanup_slack_message_cache({})

        assert result["status"] == "complete"
        assert result["deleted_count"] == 0

    async def test_cleanup_handles_multiple_batches(self):
        """Should delete in batches of 1000 and accumulate total."""
        from app.worker.tasks import cleanup_slack_message_cache

        mock_settings = MagicMock()
        mock_settings.slack_message_cache_retention_days = 7

        mock_session = AsyncMock()
        # Simulate: 1000 + 500 + 0 = 1500 total
        mock_session.execute.side_effect = [
            MagicMock(rowcount=1000),
            MagicMock(rowcount=500),
            MagicMock(rowcount=0),
        ]

        with patch("app.worker.tasks.get_db_session") as mock_ctx:
            mock_ctx.return_value.__aenter__.return_value = mock_session
            with patch("app.worker.tasks.get_settings", return_value=mock_settings):
                result = await cleanup_slack_message_cache({})

        assert result["status"] == "complete"
        assert result["deleted_count"] == 1500
        assert mock_session.execute.call_count == 3
        assert mock_session.commit.call_count == 2  # Only called for non-zero batches
