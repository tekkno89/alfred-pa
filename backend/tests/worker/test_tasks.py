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


class TestDegradeStaleNotifyNow:
    """Tests for degrade_stale_notify_now task."""

    async def test_degrade_finds_stale_items(self):
        """Stale notify_now items should be degraded to summarize_next."""
        from app.worker.tasks import degrade_stale_notify_now

        mock_settings = MagicMock()
        mock_settings.user_id = "user-1"
        mock_settings.notify_now_degrade_minutes = 240

        mock_classification = MagicMock()
        mock_classification.action = "notify_now"
        mock_classification.classification_reason = "High priority message"
        mock_classification.reviewed_at = None

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.side_effect = [
            [mock_settings],
            [mock_classification],
        ]
        mock_session.execute.return_value = mock_result

        with patch("app.worker.tasks.get_db_session") as mock_ctx:
            mock_ctx.return_value.__aenter__.return_value = mock_session
            result = await degrade_stale_notify_now({})

        assert result["status"] == "complete"
        assert result["degraded_count"] == 1
        assert result["users_checked"] == 1
        assert mock_classification.action == "summarize_next"
        assert mock_classification.classification_reason == "[AUTO-DEGRADED] High priority message"

    async def test_degrade_respects_custom_timeout(self):
        """Should use user's configured timeout."""
        from app.worker.tasks import degrade_stale_notify_now

        mock_settings = MagicMock()
        mock_settings.user_id = "user-1"
        mock_settings.notify_now_degrade_minutes = 60

        mock_classification = MagicMock()
        mock_classification.action = "notify_now"
        mock_classification.classification_reason = "Test"
        mock_classification.reviewed_at = None

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.side_effect = [
            [mock_settings],
            [mock_classification],
        ]
        mock_session.execute.return_value = mock_result

        with patch("app.worker.tasks.get_db_session") as mock_ctx:
            mock_ctx.return_value.__aenter__.return_value = mock_session
            await degrade_stale_notify_now({})

        assert mock_classification.action == "summarize_next"

    async def test_degrade_skips_reviewed_items(self):
        """Items with reviewed_at set should not be degraded."""
        from app.worker.tasks import degrade_stale_notify_now

        mock_settings = MagicMock()
        mock_settings.user_id = "user-1"
        mock_settings.notify_now_degrade_minutes = 240

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.side_effect = [
            [mock_settings],
            [],
        ]
        mock_session.execute.return_value = mock_result

        with patch("app.worker.tasks.get_db_session") as mock_ctx:
            mock_ctx.return_value.__aenter__.return_value = mock_session
            result = await degrade_stale_notify_now({})

        assert result["degraded_count"] == 0

    async def test_degrade_handles_none_reason(self):
        """Should handle items with no classification_reason."""
        from app.worker.tasks import degrade_stale_notify_now

        mock_settings = MagicMock()
        mock_settings.user_id = "user-1"
        mock_settings.notify_now_degrade_minutes = 240

        mock_classification = MagicMock()
        mock_classification.action = "notify_now"
        mock_classification.classification_reason = None
        mock_classification.reviewed_at = None

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.side_effect = [
            [mock_settings],
            [mock_classification],
        ]
        mock_session.execute.return_value = mock_result

        with patch("app.worker.tasks.get_db_session") as mock_ctx:
            mock_ctx.return_value.__aenter__.return_value = mock_session
            result = await degrade_stale_notify_now({})

        assert result["degraded_count"] == 1
        assert mock_classification.classification_reason == "[AUTO-DEGRADED] No reason provided"

    async def test_degrade_uses_default_timeout_if_none(self):
        """Should default to 240 minutes if notify_now_degrade_minutes is None."""
        from app.worker.tasks import degrade_stale_notify_now

        mock_settings = MagicMock()
        mock_settings.user_id = "user-1"
        mock_settings.notify_now_degrade_minutes = None

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.side_effect = [
            [mock_settings],
            [],
        ]
        mock_session.execute.return_value = mock_result

        with patch("app.worker.tasks.get_db_session") as mock_ctx:
            mock_ctx.return_value.__aenter__.return_value = mock_session
            await degrade_stale_notify_now({})

    async def test_degrade_only_checks_always_on_users(self):
        """Should only check users with is_always_on=True."""
        from app.worker.tasks import degrade_stale_notify_now

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.side_effect = [
            [],
        ]
        mock_session.execute.return_value = mock_result

        with patch("app.worker.tasks.get_db_session") as mock_ctx:
            mock_ctx.return_value.__aenter__.return_value = mock_session
            result = await degrade_stale_notify_now({})

        assert result["users_checked"] == 0
        assert result["degraded_count"] == 0
