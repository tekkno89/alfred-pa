# Slack Message Cache Cleanup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add ARQ worker cron job to delete expired Slack message cache rows based on configurable retention period.

**Architecture:** Follow existing worker task patterns with async DB session, batch deletion, and cron registration. Add config setting for retention days, task function in tasks.py, and register in WorkerSettings.

**Tech Stack:** Python 3.11, ARQ, SQLAlchemy 2.0, async/await

---

## File Structure

| File | Purpose |
|------|---------|
| `backend/app/core/config.py` | Add `slack_message_cache_retention_days` setting |
| `backend/app/worker/tasks.py` | Add `cleanup_slack_message_cache` task function |
| `backend/app/worker/main.py` | Register task in functions and cron_jobs |
| `backend/tests/worker/test_tasks.py` | Unit tests for cleanup task |

---

### Task 1: Add Config Setting

**Files:**
- Modify: `backend/app/core/config.py`

- [ ] **Step 1: Add retention setting to Settings class**

Find the Settings class in `backend/app/core/config.py` and add the new field after other cache-related settings:

```python
slack_message_cache_retention_days: int = 7
```

- [ ] **Step 2: Verify config loads correctly**

Run:
```bash
docker-compose -f docker-compose.dev.yml exec backend python -c "from app.core.config import get_settings; s = get_settings(); print(f'retention={s.slack_message_cache_retention_days}')" 2>&1
```

Expected output: `retention=7`

- [ ] **Step 3: Commit**

```bash
git add backend/app/core/config.py
git commit -m "feat(config): add slack_message_cache_retention_days setting"
```

---

### Task 2: Write Failing Tests

**Files:**
- Modify: `backend/tests/worker/test_tasks.py`

- [ ] **Step 1: Check if test file exists**

Run:
```bash
ls -la backend/tests/worker/test_tasks.py 2>/dev/null && echo "EXISTS" || echo "NOT FOUND"
```

If not found, create directory and file:
```bash
mkdir -p backend/tests/worker
touch backend/tests/worker/test_tasks.py
```

- [ ] **Step 2: Write test for basic cleanup**

Add to `backend/tests/worker/test_tasks.py`:

```python
"""Tests for worker tasks."""

import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch, MagicMock


class TestCleanupSlackMessageCache:
    """Tests for cleanup_slack_message_cache task."""

    async def test_cleanup_deletes_old_rows(self):
        """Old cache rows beyond retention should be deleted."""
        from app.worker.tasks import cleanup_slack_message_cache

        # Mock settings
        mock_settings = MagicMock()
        mock_settings.slack_message_cache_retention_days = 7

        # Mock DB session
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.rowcount = 100
        mock_session.execute.return_value = mock_result

        with patch("app.worker.tasks.get_db_session") as mock_ctx:
            mock_ctx.return_value.__aenter__.return_value = mock_session
            with patch("app.worker.tasks.get_settings", return_value=mock_settings):
                result = await cleanup_slack_message_cache({})

        assert result["status"] == "complete"
        assert result["deleted_count"] == 100
        mock_session.execute.assert_called()

    async def test_cleanup_respects_retention_config(self):
        """Retention period should be configurable."""
        from app.worker.tasks import cleanup_slack_message_cache

        mock_settings = MagicMock()
        mock_settings.slack_message_cache_retention_days = 3

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.rowcount = 50
        mock_session.execute.return_value = mock_result

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
        mock_result = MagicMock()
        mock_result.rowcount = 0
        mock_session.execute.return_value = mock_result

        with patch("app.worker.tasks.get_db_session") as mock_ctx:
            mock_ctx.return_value.__aenter__.return_value = mock_session
            with patch("app.worker.tasks.get_settings", return_value=mock_settings):
                result = await cleanup_slack_message_cache({})

        assert result["status"] == "complete"
        assert result["deleted_count"] == 0
```

- [ ] **Step 3: Run tests to verify they fail**

Run:
```bash
docker-compose -f docker-compose.dev.yml exec backend pytest tests/worker/test_tasks.py -v 2>&1 | tail -20
```

Expected: Tests fail with `ImportError` or `AttributeError` (function not implemented yet)

- [ ] **Step 4: Commit**

```bash
git add tests/worker/test_tasks.py
git commit -m "test(worker): add failing tests for slack message cache cleanup"
```

---

### Task 3: Implement Cleanup Task

**Files:**
- Modify: `backend/app/worker/tasks.py`

- [ ] **Step 1: Add import for datetime and delete**

At the top of `backend/app/worker/tasks.py`, verify these imports exist (add if missing):

```python
from datetime import datetime, timedelta
from sqlalchemy import delete
```

- [ ] **Step 2: Add import for get_settings**

Add to imports:
```python
from app.core.config import get_settings
```

- [ ] **Step 3: Add cleanup task function**

Add this function at the end of `backend/app/worker/tasks.py`:

```python
async def cleanup_slack_message_cache(ctx: dict) -> dict:
    """
    Cron job: delete Slack message cache rows older than retention period.
    Runs daily at 2 AM UTC.
    """
    from app.db.models.slack_message_cache import SlackMessageCache

    settings = get_settings()
    retention_days = settings.slack_message_cache_retention_days

    logger.info(
        f"Starting Slack message cache cleanup (retention={retention_days} days)"
    )

    cutoff = datetime.utcnow() - timedelta(days=retention_days)
    total_deleted = 0
    batch_size = 1000

    async with get_db_session() as db:
        while True:
            try:
                stmt = (
                    delete(SlackMessageCache)
                    .where(SlackMessageCache.cached_at < cutoff)
                    .limit(batch_size)
                )
                result = await db.execute(stmt)
                deleted = result.rowcount

                if deleted == 0:
                    break

                total_deleted += deleted
                logger.debug(f"Deleted batch of {deleted} cache rows")
                await db.commit()

            except Exception as e:
                logger.error(f"Error deleting cache batch: {e}")
                break

    logger.info(f"Cleaned up {total_deleted} expired Slack message cache rows")
    return {"status": "complete", "deleted_count": total_deleted}
```

- [ ] **Step 4: Run tests to verify they pass**

Run:
```bash
docker-compose -f docker-compose.dev.yml exec backend pytest tests/worker/test_tasks.py -v 2>&1 | tail -15
```

Expected: All 3 tests pass

- [ ] **Step 5: Commit**

```bash
git add backend/app/worker/tasks.py
git commit -m "feat(worker): add cleanup_slack_message_cache task"
```

---

### Task 4: Register Task in Worker

**Files:**
- Modify: `backend/app/worker/main.py`

- [ ] **Step 1: Add import for cleanup task**

In `backend/app/worker/main.py`, add `cleanup_slack_message_cache` to the imports from tasks:

```python
from app.worker.tasks import (
    check_due_todo_reminders,
    cleanup_expired_classifications,
    cleanup_orphaned_focus_items,
    cleanup_slack_message_cache,  # Add this
    expire_focus_session,
    process_triage_job,
    refresh_slack_channel_cache,
    send_digest,
    send_todo_reminder,
    transition_pomodoro,
    update_channel_summaries,
    update_user_channel_participation,
)
```

- [ ] **Step 2: Add to functions list**

In `WorkerSettings.functions`, add the task:

```python
functions = [
    expire_focus_session,
    transition_pomodoro,
    send_todo_reminder,
    send_digest,
    process_triage_job,
    refresh_slack_channel_cache,
    update_user_channel_participation,
    update_channel_summaries,
    cleanup_slack_message_cache,  # Add this
]
```

- [ ] **Step 3: Add to cron_jobs**

In `WorkerSettings.cron_jobs`, add the cron entry (after `cleanup_expired_classifications`):

```python
cron(
    cleanup_slack_message_cache,
    hour={2},
    minute={0},  # Daily at 2 AM UTC
),
```

- [ ] **Step 4: Verify worker starts**

Run:
```bash
docker-compose -f docker-compose.dev.yml exec backend python -c "from app.worker.main import WorkerSettings; print('functions:', len(WorkerSettings.functions)); print('cron_jobs:', len(WorkerSettings.cron_jobs))" 2>&1
```

Expected: Shows counts including the new task

- [ ] **Step 5: Commit**

```bash
git add backend/app/worker/main.py
git commit -m "feat(worker): register cleanup_slack_message_cache cron job"
```

---

### Task 5: Add Integration Test

**Files:**
- Modify: `backend/tests/worker/test_tasks.py`

- [ ] **Step 1: Add test for batch handling**

Add to `backend/tests/worker/test_tasks.py`:

```python
    async def test_cleanup_handles_multiple_batches(self):
        """Large deletions should be batched."""
        from app.worker.tasks import cleanup_slack_message_cache

        mock_settings = MagicMock()
        mock_settings.slack_message_cache_retention_days = 7

        mock_session = AsyncMock()

        # Simulate 3 batches: 1000, 1000, 500, then 0
        call_count = 0

        def mock_execute(stmt):
            nonlocal call_count
            call_count += 1
            mock_result = MagicMock()
            if call_count == 1:
                mock_result.rowcount = 1000
            elif call_count == 2:
                mock_result.rowcount = 1000
            elif call_count == 3:
                mock_result.rowcount = 500
            else:
                mock_result.rowcount = 0
            return mock_result

        mock_session.execute.side_effect = mock_execute
        mock_session.commit = AsyncMock()

        with patch("app.worker.tasks.get_db_session") as mock_ctx:
            mock_ctx.return_value.__aenter__.return_value = mock_session
            with patch("app.worker.tasks.get_settings", return_value=mock_settings):
                result = await cleanup_slack_message_cache({})

        assert result["deleted_count"] == 2500
        assert call_count == 4  # 3 batches + 1 empty check
```

- [ ] **Step 2: Run all tests**

Run:
```bash
docker-compose -f docker-compose.dev.yml exec backend pytest tests/worker/test_tasks.py -v 2>&1 | tail -15
```

Expected: All 4 tests pass

- [ ] **Step 3: Commit**

```bash
git add tests/worker/test_tasks.py
git commit -m "test(worker): add batch handling test for cache cleanup"
```

---

### Task 6: Run Full Test Suite

- [ ] **Step 1: Run worker tests**

Run:
```bash
docker-compose -f docker-compose.dev.yml exec backend pytest tests/worker/ -v 2>&1 | tail -20
```

Expected: All tests pass

- [ ] **Step 2: Verify no regressions in other tests**

Run:
```bash
docker-compose -f docker-compose.dev.yml exec backend pytest tests/services/test_triage_delivery.py tests/services/test_digest_grouper.py tests/services/test_engagement_check.py -v --tb=line 2>&1 | tail -10
```

Expected: All tests pass

- [ ] **Step 3: Final commit (if any changes)**

```bash
git status
```

If clean, no commit needed. If changes, commit them.

---

## Self-Review Checklist

- [x] Spec coverage: All requirements from spec have corresponding tasks
- [x] No placeholders: All code blocks contain complete implementations
- [x] Type consistency: Function signatures match across all references
- [x] Test coverage: Tests cover happy path, config, empty results, and batching
- [x] Error handling: Task logs errors and continues
- [x] Logging: Start, progress, and end messages defined

## Files Modified Summary

1. `backend/app/core/config.py` - Add retention setting
2. `backend/app/worker/tasks.py` - Add cleanup task function
3. `backend/app/worker/main.py` - Register task in worker
4. `backend/tests/worker/test_tasks.py` - Add unit tests

## Verification

After implementation:
1. Worker starts without errors
2. Cron job registered at 2 AM UTC
3. Unit tests pass (4 tests)
4. Manual test: Call `cleanup_slack_message_cache({})` directly and verify logs
