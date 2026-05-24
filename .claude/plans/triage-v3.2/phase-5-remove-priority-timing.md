# Remove Old Priority-Based Timing Controls

> **Status: ✅ COMPLETE** (2026-05-17)

**Goal:** Remove the old priority-based timing controls (`p0/p1/p2/p3_alerts_enabled`, `p1/p2_digest_*` fields) and replace them with the new action-based smart delivery system.

**Architecture:** The old system used priority labels (P0-P3) with configurable intervals, scheduled times, and active hours. The new system uses action labels (`notify_now`, `summarize_next`, `summarize_eod`, `ignore`) with smart delivery triggers (calendar, idle, stale queue) and per-type adaptive windows. This migration removes the old fields from model, schema, and UI while preserving user data during transition.

**Tech Stack:** Python 3.11+, FastAPI, SQLAlchemy 2.0, Alembic, React, TypeScript

---

## Background: What's Being Removed

### Model Fields (TriageUserSettings)
- `p0_alerts_enabled` - was used to gate notify_now
- `p1_alerts_enabled` - was used to gate summarize_next
- `p2_alerts_enabled` - was used to gate summarize_eod
- `p3_alerts_enabled` - was used to gate ignore
- `p1_digest_interval_minutes` - interval for P1 digests
- `p1_digest_times` - scheduled times for P1 digests
- `p1_digest_active_hours_start` - active hours start for P1
- `p1_digest_active_hours_end` - active hours end for P1
- `p1_digest_outside_hours_behavior` - behavior outside active hours
- `p2_digest_interval_minutes` - interval for P2 digests
- `p2_digest_times` - scheduled times for P2 digests
- `p2_digest_active_hours_start` - active hours start for P2
- `p2_digest_active_hours_end` - active hours end for P2
- `p2_digest_outside_hours_behavior` - behavior outside active hours
- `p3_digest_time` - time for P3/EOD digest

### Services Affected
- `digest_scheduler.py` - heavily uses old fields, will be deprecated
- `triage_pipeline.py` - uses `p0/p1/p2/p3_alerts_enabled` for gating

### Frontend Affected
- `TriageSettingsPage.tsx` - has extensive "Alert Cadence" UI section

---

## New System Already Implemented

The following Phase 4 features replace the old system:
- `DigestDeliveryOrchestrator` with smart triggers
- `AdaptiveWindowService` with per-type windows
- `eod_review_time` for EOD digest timing
- `notify_now_degrade_minutes` for auto-degrade
- `away_mode_enabled` and `away_mode_notify_now_behavior`

---

## File Structure

### Migrations
- Create: `backend/alembic/versions/052_remove_priority_timing_fields.py`

### Backend Modified
- `backend/app/db/models/triage.py` - Remove 15 fields
- `backend/app/schemas/triage.py` - Remove 15 fields from Update/Response
- `backend/app/services/triage_pipeline.py` - Remove alert gating logic
- `backend/app/services/digest_scheduler.py` - Deprecate or remove

### Frontend Modified
- `frontend/src/types/index.ts` - Remove 15 fields
- `frontend/src/pages/TriageSettingsPage.tsx` - Remove Alert Cadence UI

---

## Task 1: Create Migration to Remove Old Fields

**Files:**
- Create: `backend/alembic/versions/052_remove_priority_timing_fields.py`

- [ ] **Step 1: Create migration file**

```python
# backend/alembic/versions/052_remove_priority_timing_fields.py
"""remove priority-based timing fields

Revision ID: 052
Revises: 051
"""

from alembic import op
import sqlalchemy as sa

revision = '052'
down_revision = '051'
depends_on = None


def upgrade() -> None:
    # Remove alert enabled fields
    op.drop_column('triage_user_settings', 'p0_alerts_enabled')
    op.drop_column('triage_user_settings', 'p1_alerts_enabled')
    op.drop_column('triage_user_settings', 'p2_alerts_enabled')
    op.drop_column('triage_user_settings', 'p3_alerts_enabled')
    
    # Remove P1 digest fields
    op.drop_column('triage_user_settings', 'p1_digest_interval_minutes')
    op.drop_column('triage_user_settings', 'p1_digest_times')
    op.drop_column('triage_user_settings', 'p1_digest_active_hours_start')
    op.drop_column('triage_user_settings', 'p1_digest_active_hours_end')
    op.drop_column('triage_user_settings', 'p1_digest_outside_hours_behavior')
    
    # Remove P2 digest fields
    op.drop_column('triage_user_settings', 'p2_digest_interval_minutes')
    op.drop_column('triage_user_settings', 'p2_digest_times')
    op.drop_column('triage_user_settings', 'p2_digest_active_hours_start')
    op.drop_column('triage_user_settings', 'p2_digest_active_hours_end')
    op.drop_column('triage_user_settings', 'p2_digest_outside_hours_behavior')
    
    # Remove P3 digest field
    op.drop_column('triage_user_settings', 'p3_digest_time')


def downgrade() -> None:
    # Re-add alert enabled fields
    op.add_column(
        'triage_user_settings',
        sa.Column('p0_alerts_enabled', sa.Boolean(), server_default='true')
    )
    op.add_column(
        'triage_user_settings',
        sa.Column('p1_alerts_enabled', sa.Boolean(), server_default='true')
    )
    op.add_column(
        'triage_user_settings',
        sa.Column('p2_alerts_enabled', sa.Boolean(), server_default='true')
    )
    op.add_column(
        'triage_user_settings',
        sa.Column('p3_alerts_enabled', sa.Boolean(), server_default='true')
    )
    
    # Re-add P1 digest fields
    op.add_column(
        'triage_user_settings',
        sa.Column('p1_digest_interval_minutes', sa.Integer(), nullable=True)
    )
    op.add_column(
        'triage_user_settings',
        sa.Column('p1_digest_times', sa.JSON(), nullable=True)
    )
    op.add_column(
        'triage_user_settings',
        sa.Column('p1_digest_active_hours_start', sa.String(10), nullable=True)
    )
    op.add_column(
        'triage_user_settings',
        sa.Column('p1_digest_active_hours_end', sa.String(10), nullable=True)
    )
    op.add_column(
        'triage_user_settings',
        sa.Column('p1_digest_outside_hours_behavior', sa.String(20), nullable=True)
    )
    
    # Re-add P2 digest fields
    op.add_column(
        'triage_user_settings',
        sa.Column('p2_digest_interval_minutes', sa.Integer(), nullable=True)
    )
    op.add_column(
        'triage_user_settings',
        sa.Column('p2_digest_times', sa.JSON(), nullable=True)
    )
    op.add_column(
        'triage_user_settings',
        sa.Column('p2_digest_active_hours_start', sa.String(10), nullable=True)
    )
    op.add_column(
        'triage_user_settings',
        sa.Column('p2_digest_active_hours_end', sa.String(10), nullable=True)
    )
    op.add_column(
        'triage_user_settings',
        sa.Column('p2_digest_outside_hours_behavior', sa.String(20), nullable=True)
    )
    
    # Re-add P3 digest field
    op.add_column(
        'triage_user_settings',
        sa.Column('p3_digest_time', sa.String(10), nullable=True)
    )
```

- [ ] **Step 2: Run migration**

```bash
docker-compose -f docker-compose.dev.yml exec backend alembic upgrade head
```

Expected: Migration applies successfully, revision becomes 052.

- [ ] **Step 3: Commit**

```bash
git add backend/alembic/versions/052_remove_priority_timing_fields.py
git commit -m "feat(triage): add migration to remove priority timing fields"
```

---

## Task 2: Remove Fields from Model

**Files:**
- Modify: `backend/app/db/models/triage.py`

- [ ] **Step 1: Remove the 15 old fields from TriageUserSettings**

Find the TriageUserSettings class and remove these field definitions:
- `p0_alerts_enabled`
- `p1_alerts_enabled`
- `p2_alerts_enabled`
- `p3_alerts_enabled`
- `p1_digest_interval_minutes`
- `p1_digest_times`
- `p1_digest_active_hours_start`
- `p1_digest_active_hours_end`
- `p1_digest_outside_hours_behavior`
- `p2_digest_interval_minutes`
- `p2_digest_times`
- `p2_digest_active_hours_start`
- `p2_digest_active_hours_end`
- `p2_digest_outside_hours_behavior`
- `p3_digest_time`

Keep these fields (they are the new system):
- `eod_review_time`
- `notify_now_degrade_minutes`
- `away_mode_enabled`
- `away_mode_notify_now_behavior`
- `product_mode`

- [ ] **Step 2: Commit**

```bash
git add backend/app/db/models/triage.py
git commit -m "refactor(triage): remove old priority timing fields from model"
```

---

## Task 3: Remove Fields from Schemas

**Files:**
- Modify: `backend/app/schemas/triage.py`

- [ ] **Step 1: Remove fields from TriageSettingsUpdate**

Remove these fields from the `TriageSettingsUpdate` class:
- `p0_alerts_enabled`
- `p1_alerts_enabled`
- `p2_alerts_enabled`
- `p3_alerts_enabled`
- `p1_digest_interval_minutes`
- `p1_digest_times`
- `p1_digest_active_hours_start`
- `p1_digest_active_hours_end`
- `p1_digest_outside_hours_behavior`
- `p2_digest_interval_minutes`
- `p2_digest_times`
- `p2_digest_active_hours_start`
- `p2_digest_active_hours_end`
- `p2_digest_outside_hours_behavior`
- `p3_digest_time`

- [ ] **Step 2: Remove fields from TriageSettingsResponse**

Remove the same 15 fields from `TriageSettingsResponse` class.

- [ ] **Step 3: Commit**

```bash
git add backend/app/schemas/triage.py
git commit -m "refactor(triage): remove old priority timing fields from schemas"
```

---

## Task 4: Update TriagePipeline to Remove Alert Gating

**Files:**
- Modify: `backend/app/services/triage_pipeline.py`

- [ ] **Step 1: Remove alerts_enabled check**

Find and remove this code block (around lines 157-177):

```python
# OLD CODE TO REMOVE:
alerts_enabled = {
    "notify_now": settings.p0_alerts_enabled if settings else True,
    "summarize_next": settings.p1_alerts_enabled if settings else True,
    "summarize_eod": settings.p2_alerts_enabled if settings else True,
    "ignore": settings.p3_alerts_enabled if settings else True,
}.get(action, True)

if not alerts_enabled:
    from datetime import datetime
    classification.last_alerted_at = datetime.utcnow()
    classification.queued_for_digest = False
    logger.info(
        f"{action} alerts disabled for user {user_id}, "
        f"marking classification as alerted immediately"
    )
else:
    if action in ("summarize_next", "summarize_eod"):
        classification.queued_for_digest = True
    else:
        classification.queued_for_digest = False
```

- [ ] **Step 2: Replace with simpler logic**

Replace the removed code with:

```python
# Queue summarize_next and summarize_eod for digest
if action in ("summarize_next", "summarize_eod"):
    classification.queued_for_digest = True
else:
    classification.queued_for_digest = False
```

- [ ] **Step 3: Remove p0_alerts_enabled check**

Find and remove this code (around lines 182-187):

```python
# OLD CODE TO REMOVE:
p0_enabled = settings.p0_alerts_enabled if settings else True

if not p0_enabled:
    logger.info(
        f"notify_now alerts disabled for user {user_id}, skipping notification"
    )
else:
```

Replace with just the notification logic (no conditional).

- [ ] **Step 4: Commit**

```bash
git add backend/app/services/triage_pipeline.py
git commit -m "refactor(triage): remove priority alert gating from pipeline"
```

---

## Task 5: Deprecate DigestScheduler

**Files:**
- Modify: `backend/app/services/digest_scheduler.py`
- Modify: `backend/app/worker/tasks.py`
- Modify: `backend/app/worker/main.py`

- [ ] **Step 1: Add deprecation notice to digest_scheduler.py**

Add at the top of the file:

```python
"""
Digest scheduling service for configurable alert cadence.

DEPRECATED: This service is deprecated in favor of DigestDeliveryOrchestrator.
The old priority-based timing controls (p0/p1/p2/p3_alerts_enabled, 
p1/p2_digest_interval_minutes, etc.) have been removed.

This file is kept for reference but should not be used for new development.
"""
import warnings

warnings.warn(
    "DigestScheduler is deprecated. Use DigestDeliveryOrchestrator instead.",
    DeprecationWarning,
    stacklevel=2,
)
```

- [ ] **Step 2: Remove schedule_digest_jobs from worker tasks**

In `backend/app/worker/tasks.py`, find and remove the `schedule_digest_jobs` task if it exists.

- [ ] **Step 3: Remove cron job from main.py**

In `backend/app/worker/main.py`, remove any cron job that calls `schedule_digest_jobs`.

- [ ] **Step 4: Commit**

```bash
git add backend/app/services/digest_scheduler.py \
        backend/app/worker/tasks.py \
        backend/app/worker/main.py
git commit -m "deprecate(triage): deprecate DigestScheduler in favor of orchestrator"
```

---

## Task 6: Remove Frontend Types

**Files:**
- Modify: `frontend/src/types/index.ts`

- [ ] **Step 1: Remove fields from TriageSettings interface**

Remove these fields from the `TriageSettings` interface:
- `p0_alerts_enabled`
- `p1_alerts_enabled`
- `p2_alerts_enabled`
- `p3_alerts_enabled`
- `p1_digest_interval_minutes`
- `p1_digest_times`
- `p1_digest_active_hours_start`
- `p1_digest_active_hours_end`
- `p1_digest_outside_hours_behavior`
- `p2_digest_interval_minutes`
- `p2_digest_times`
- `p2_digest_active_hours_start`
- `p2_digest_active_hours_end`
- `p2_digest_outside_hours_behavior`
- `p3_digest_time`

- [ ] **Step 2: Remove fields from TriageSettingsUpdate interface**

Remove the same 15 fields from `TriageSettingsUpdate` interface.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/types/index.ts
git commit -m "refactor(triage): remove old priority timing fields from types"
```

---

## Task 7: Remove Alert Cadence UI from TriageSettingsPage

**Files:**
- Modify: `frontend/src/pages/TriageSettingsPage.tsx`

- [ ] **Step 1: Remove state variables**

Remove all state variables related to old timing controls:
- `p1Mode`, `p2Mode`
- `p0AlertsEnabled`, `p1AlertsEnabled`, `p2AlertsEnabled`, `p3AlertsEnabled`
- `alertDedupWindow`
- `p1Interval`, `p1ActiveHoursStart`, `p1ActiveHoursEnd`, `p1OutsideHoursBehavior`, `p1Times`
- `p2Interval`, `p2ActiveHoursStart`, `p2ActiveHoursEnd`, `p2OutsideHoursBehavior`, `p2Times`
- `p3Time`

- [ ] **Step 2: Remove useEffect for mode updates**

Remove the useEffect that sets p1Mode/p2Mode from settings.

- [ ] **Step 3: Remove hasChanges logic for old fields**

Remove the change detection for old fields from the `hasChanges` variable.

- [ ] **Step 4: Remove the "Alert Cadence" Card section**

Remove the entire Card component that contains the Alert Cadence UI. This is a large section (~300 lines) containing:
- P0 Alerts toggle
- P1 Alerts section (toggle, interval/scheduled mode, times, active hours)
- P2 Alerts section (toggle, interval/scheduled mode, times, active hours)
- P3 Alerts section (toggle, EOD time)
- Save button for cadence changes

- [ ] **Step 5: Update the save handler**

Remove the logic that builds the payload with old fields (lines 769-815).

- [ ] **Step 6: Keep these new sections**

Ensure these sections remain:
- General settings card (always_on, debug_mode, etc.)
- Away Mode toggle
- Adaptive Windows card
- Custom Classification Rules
- Channel Rules

- [ ] **Step 7: Verify frontend builds**

```bash
cd frontend && npm run build
```

Expected: Build succeeds with no TypeScript errors.

- [ ] **Step 8: Commit**

```bash
git add frontend/src/pages/TriageSettingsPage.tsx
git commit -m "refactor(triage): remove old alert cadence UI from settings"
```

---

## Task 8: Update Tests

**Files:**
- Modify: `backend/tests/api/test_triage_settings.py`
- Modify: `backend/tests/services/test_digest_scheduler.py` (if exists)

- [ ] **Step 1: Remove tests for old fields**

Remove any tests that test `p0_alerts_enabled`, `p1_digest_interval_minutes`, etc.

- [ ] **Step 2: Update test fixtures**

Update any test fixtures that set old fields to remove them.

- [ ] **Step 3: Run tests**

```bash
docker-compose -f docker-compose.dev.yml exec backend pytest tests/api/test_triage_settings.py -v
```

Expected: Tests pass (may have some failures to fix).

- [ ] **Step 4: Commit**

```bash
git add backend/tests/
git commit -m "test(triage): update tests for removed priority timing fields"
```

---

## Task 9: Final Verification

- [ ] **Step 1: Run all backend tests**

```bash
docker-compose -f docker-compose.dev.yml exec backend pytest -v --tb=short
```

Expected: All tests pass or pre-existing failures only.

- [ ] **Step 2: Build frontend**

```bash
cd frontend && npm run build
```

Expected: Build succeeds.

- [ ] **Step 3: Check migration status**

```bash
docker-compose -f docker-compose.dev.yml exec backend alembic current
```

Expected: Shows `052 (head)`.

- [ ] **Step 4: Commit any remaining changes**

```bash
git add -A
git status
```

Expected: No uncommitted changes.

---

## Acceptance Criteria

- [x] All 15 old priority timing fields removed from model
- [x] All 15 fields removed from schemas
- [x] Migration 052 drops the columns
- [x] TriagePipeline no longer uses `p0/p1/p2/p3_alerts_enabled`
- [x] DigestScheduler deprecated
- [x] Frontend Alert Cadence UI removed (504 lines)
- [x] Frontend types updated
- [x] Tests updated
- [x] Frontend builds successfully
- [x] Backend tests pass (42 tests)

---

## User Migration Notes

Users will lose their old timing configuration (intervals, scheduled times, active hours). The new system provides:

- **EOD Review Time**: User sets when to receive end-of-day digest (already implemented)
- **Smart Delivery**: No configuration needed - Alfred detects idle/calendar
- **Adaptive Windows**: Learns from engagement automatically
- **Away Mode**: Manual toggle for queuing messages

No data migration is needed because the old settings are replaced by the new system behavior.

---

*Plan complete. Ready for execution.*
