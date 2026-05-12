# Slack Message Cache Cleanup Worker Task

**Date**: 2026-05-11
**Status**: Approved

## Overview

Add an ARQ worker cron job to delete expired Slack message cache rows based on configurable retention period.

## Requirements

1. Delete cached Slack messages older than retention period
2. Run daily via cron job
3. Configurable retention period via environment variable
4. Batch deletion to avoid DB overload
5. Graceful error handling with logging

## Technical Design

### Configuration

**File**: `backend/app/core/config.py`

Add new setting:
```python
slack_message_cache_retention_days: int = 7
```

Environment variable: `SLACK_MESSAGE_CACHE_RETENTION_DAYS`

### Task Function

**File**: `backend/app/worker/tasks.py`

```python
async def cleanup_slack_message_cache(ctx: dict) -> dict:
    """
    Cron job: delete Slack message cache rows older than retention period.
    Runs daily at 2 AM UTC.
    """
```

**Logic**:
1. Get retention days from settings (default 7)
2. Calculate cutoff timestamp: `now() - retention_days`
3. Query `slack_message_cache` for rows where `cached_at < cutoff`
4. Delete in batches of 1,000 rows
5. Log progress and total count
6. Return summary with `deleted_count`

**Batch handling**:
- Loop until no more rows to delete
- Each iteration: DELETE with LIMIT 1000
- Catch exceptions per batch, log, continue
- Commit after each successful batch

### Cron Registration

**File**: `backend/app/worker/main.py`

Add to `WorkerSettings.cron_jobs`:
```python
cron(
    cleanup_slack_message_cache,
    hour={2},
    minute={0},  # Daily at 2 AM UTC
),
```

Add to `WorkerSettings.functions`:
```python
cleanup_slack_message_cache,
```

### Error Handling

- Wrap batch deletion in try/except
- Log error with row count and continue to next batch
- Return partial success count if some batches fail
- Never raise exception (cron job should always complete)

### Logging

- INFO: Start message with retention period
- DEBUG: Per-batch deletion count
- INFO: Final summary with total deleted
- ERROR: Batch failures (continue processing)

## Testing

**File**: `backend/tests/worker/test_tasks.py`

Test cases:
1. `test_cleanup_slack_message_cache_deletes_old_rows`
   - Create cache rows with `cached_at` older than retention
   - Verify they are deleted
   - Verify recent rows are preserved

2. `test_cleanup_slack_message_cache_respects_retention_config`
   - Set retention to 3 days
   - Create rows at 2, 4, 6 days old
   - Verify only 2-day-old rows preserved

3. `test_cleanup_slack_message_cache_handles_batches`
   - Create 2500 old rows
   - Verify deletion happens in batches of 1000
   - Verify all old rows deleted

4. `test_cleanup_slack_message_cache_handles_errors_gracefully`
   - Mock DB to raise exception on second batch
   - Verify first batch succeeds and is logged
   - Verify task completes with partial count

## Migration

No migration needed - uses existing `slack_message_cache` table.

## Rollout

1. Add config setting with default 7 days
2. Add task function
3. Register cron job
4. Deploy to staging, verify logs
5. Deploy to production

## Success Criteria

- [ ] Cron job runs daily at 2 AM UTC
- [ ] Old cache rows deleted (verified via logs)
- [ ] No DB performance degradation
- [ ] Unit tests pass
