# Phase 4: Timing Optimization

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Implement smart delivery with pluggable triggers, adaptive windows, notify_now auto-degrade, and away mode primitives.

**Duration:** 2 weeks

**Architecture:** `DigestDeliveryOrchestrator` replaces `digest_scheduler` with pluggable triggers (calendar end, idle, escalation, stale-queue ceiling). Per-type adaptive delivery windows with EMA learning. Away mode with manual toggle and queue-for-catch-up option.

**Tech Stack:** Python 3.11+, FastAPI, SQLAlchemy, Redis, Google Calendar API

---

## Requirements Covered

- **R5:** Smart delivery with pluggable triggers
- **R-AwayMode:** Manual away mode with catch-up digest
- Per-type adaptive delivery windows (R5c)
- notify_now auto-degrade (R5a)
- Focus mode delivery interaction

---

## File Structure

### Create

```
backend/app/services/digest_delivery_orchestrator.py
backend/alembic/versions/050_add_triage_user_settings_new_fields.py
backend/app/api/triage_away_mode.py
frontend/src/components/triage/AwayModeToggle.tsx
frontend/src/components/triage/AdaptiveWindowsCard.tsx
```

### Modify

```
backend/app/db/models/triage.py (TriageUserSettings)
backend/app/worker/tasks.py
backend/app/schemas/triage.py
backend/app/services/triage_pipeline.py
```

---

## Task 1: Add new TriageUserSettings fields

**Files:**
- Create: `backend/alembic/versions/050_add_triage_user_settings_new_fields.py`
- Modify: `backend/app/db/models/triage.py`
- Modify: `backend/app/schemas/triage.py`

### Step 1: Create migration

- [ ] **Create migration file**

```python
# backend/alembic/versions/050_add_triage_user_settings_new_fields.py
"""add triage user settings new fields

Revision ID: 050
Revises: 049
"""

from alembic import op
import sqlalchemy as sa

revision = '050'
down_revision = '049'
depends_on = None


def upgrade() -> None:
    op.add_column(
        'triage_user_settings',
        sa.Column('eod_review_time', sa.String(10), server_default='17:30')
    )
    op.add_column(
        'triage_user_settings',
        sa.Column('notify_now_degrade_minutes', sa.Integer, server_default='240')
    )
    op.add_column(
        'triage_user_settings',
        sa.Column('away_mode_enabled', sa.Boolean, server_default='false')
    )
    op.add_column(
        'triage_user_settings',
        sa.Column('away_mode_notify_now_behavior', sa.String(20), server_default='push_immediately')
    )
    op.add_column(
        'triage_user_settings',
        sa.Column('product_mode', sa.String(20), server_default='always_on')
    )


def downgrade() -> None:
    op.drop_column('triage_user_settings', 'product_mode')
    op.drop_column('triage_user_settings', 'away_mode_notify_now_behavior')
    op.drop_column('triage_user_settings', 'away_mode_enabled')
    op.drop_column('triage_user_settings', 'notify_now_degrade_minutes')
    op.drop_column('triage_user_settings', 'eod_review_time')
```

### Step 2: Update model

- [ ] **Update TriageUserSettings**

```python
# backend/app/db/models/triage.py
# Add fields to TriageUserSettings:

    # Phase 4: Smart delivery settings
    eod_review_time: Mapped[str] = mapped_column(
        String(10), default="17:30", server_default="17:30"
    )
    notify_now_degrade_minutes: Mapped[int] = mapped_column(
        Integer, default=240, server_default="240"
    )
    
    # Away mode
    away_mode_enabled: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false"
    )
    away_mode_notify_now_behavior: Mapped[str] = mapped_column(
        String(20), default="push_immediately", server_default="push_immediately"
    )
    
    # Product mode: always_on | focus_bounded
    product_mode: Mapped[str] = mapped_column(
        String(20), default="always_on", server_default="always_on"
    )
```

### Step 3: Update schemas

- [ ] **Update schemas**

```python
# backend/app/schemas/triage.py

class TriageSettingsUpdate(BaseModel):
    # ... existing fields ...
    
    # Phase 4 fields
    eod_review_time: str | None = Field(None, pattern="^([01]?[0-9]|2[0-3]):[0-5][0-9]$")
    notify_now_degrade_minutes: int | None = Field(None, ge=30, le=1440)
    away_mode_enabled: bool | None = None
    away_mode_notify_now_behavior: str | None = Field(
        None, pattern="^(push_immediately|queue_for_catch_up)$"
    )
    product_mode: str | None = Field(None, pattern="^(always_on|focus_bounded)$")


class TriageSettingsResponse(BaseModel):
    # ... existing fields ...
    
    # Phase 4 fields
    eod_review_time: str = "17:30"
    notify_now_degrade_minutes: int = 240
    away_mode_enabled: bool = False
    away_mode_notify_now_behavior: str = "push_immediately"
    product_mode: str = "always_on"
```

### Step 4: Run migration

```bash
docker-compose -f docker-compose.dev.yml exec backend alembic upgrade head
```

### Step 5: Commit

```bash
git add backend/alembic/versions/050_add_triage_user_settings_new_fields.py \
        backend/app/db/models/triage.py \
        backend/app/schemas/triage.py
git commit -m "feat(triage): add smart delivery and away mode settings"
```

---

## Task 2: Create DigestDeliveryOrchestrator

**Files:**
- Create: `backend/app/services/digest_delivery_orchestrator.py`
- Modify: `backend/app/worker/tasks.py` (replace digest_scheduler references)

### Step 1: Create orchestrator

- [ ] **Create service file**

```python
# backend/app/services/digest_delivery_orchestrator.py
"""Smart delivery orchestrator with pluggable triggers (R5).

Replaces digest_scheduler.py with more sophisticated trigger logic.

Triggers for summarize_next delivery:
1. End-of-meeting (calendar event ends, no immediate next event)
2. Idle detection (Slack presence away ≥10 min, OR no calendar event)
3. Escalation push (R2c promoted to notify_now)
4. Stale-queue ceiling (per-type window reaches limit)

Focus mode interaction:
- Focus-bounded mode: no summarize_next deliveries during focus sessions
- Always-on mode: focus suppresses non-escalation deliveries
"""

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.triage import TriageClassification, TriageUserSettings
from app.db.repositories.triage import TriageUserSettingsRepository

if TYPE_CHECKING:
    from app.services.calendar import CalendarService
    from app.services.focus import FocusModeService

logger = logging.getLogger(__name__)


@dataclass
class DeliveryTrigger:
    """A trigger that fired for delivery."""
    trigger_type: str  # 'calendar_end', 'idle', 'escalation', 'stale_queue'
    user_id: str
    triggered_at: datetime
    metadata: dict


class DeliveryTriggerPlugin(ABC):
    """Base class for delivery trigger plugins."""

    @abstractmethod
    async def check(self, user_id: str, settings: TriageUserSettings) -> DeliveryTrigger | None:
        """Check if this trigger should fire.

        Returns DeliveryTrigger if fired, None otherwise.
        """
        pass


class CalendarEndTrigger(DeliveryTriggerPlugin):
    """Trigger when calendar event ends with no immediate next event."""

    def __init__(self, calendar_service: "CalendarService") -> None:
        self.calendar = calendar_service

    async def check(self, user_id: str, settings: TriageUserSettings) -> DeliveryTrigger | None:
        """Check if a calendar event just ended."""
        try:
            # Get current and upcoming events
            now = datetime.utcnow()
            events = await self.calendar.get_events(
                user_id=user_id,
                time_min=now - timedelta(minutes=30),
                time_max=now + timedelta(hours=1),
            )

            # Find event that just ended
            for event in events:
                end_time = event.get("end", {}).get("dateTime")
                if not end_time:
                    continue

                # Parse end time
                # (simplified - use proper datetime parsing)
                event_end = datetime.fromisoformat(end_time.replace("Z", "+00:00"))
                time_since_end = (now - event_end.replace(tzinfo=None)).total_seconds()

                # Event ended 0-5 minutes ago
                if 0 <= time_since_end <= 300:
                    # Check if there's an immediate next event
                    next_event_start = None
                    for other in events:
                        if other["id"] == event["id"]:
                            continue
                        start = other.get("start", {}).get("dateTime")
                        if start:
                            other_start = datetime.fromisoformat(start.replace("Z", "+00:00"))
                            if other_start > event_end:
                                if next_event_start is None or other_start < next_event_start:
                                    next_event_start = other_start

                    # No next event within 15 min
                    if next_event_start is None or (next_event_start - event_end).total_seconds() > 900:
                        return DeliveryTrigger(
                            trigger_type="calendar_end",
                            user_id=user_id,
                            triggered_at=now,
                            metadata={"event_summary": event.get("summary")},
                        )

            return None

        except Exception as e:
            logger.warning(f"Calendar end trigger check failed: {e}")
            return None


class IdleTrigger(DeliveryTriggerPlugin):
    """Trigger when user is idle (Slack away ≥10 min or no calendar event)."""

    IDLE_THRESHOLD_MINUTES = 10

    async def check(self, user_id: str, settings: TriageUserSettings) -> DeliveryTrigger | None:
        """Check if user is idle."""
        # This would check Slack presence and calendar
        # Simplified for Phase 4
        return None


class StaleQueueTrigger(DeliveryTriggerPlugin):
    """Trigger when per-type queue reaches window limit."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def check(self, user_id: str, settings: TriageUserSettings) -> DeliveryTrigger | None:
        """Check if any queue is stale."""
        # Get per-type window limits (would come from adaptive windows)
        # For now, check if summarize_next items are > 30 min old
        cutoff = datetime.utcnow() - timedelta(minutes=30)

        result = await self.db.execute(
            select(TriageClassification).where(
                and_(
                    TriageClassification.user_id == user_id,
                    TriageClassification.action == "summarize_next",
                    TriageClassification.created_at < cutoff,
                    TriageClassification.reviewed_at.is_(None),
                )
            )
        )
        stale = result.scalars().all()

        if stale:
            return DeliveryTrigger(
                trigger_type="stale_queue",
                user_id=user_id,
                triggered_at=datetime.utcnow(),
                metadata={"stale_count": len(stale)},
            )

        return None


class DigestDeliveryOrchestrator:
    """Orchestrates digest delivery with pluggable triggers.

    Replaces digest_scheduler with more sophisticated delivery logic.
    """

    def __init__(
        self,
        db: AsyncSession,
        calendar_service: "CalendarService | None" = None,
        focus_service: "FocusModeService | None" = None,
    ) -> None:
        self.db = db
        self.settings_repo = TriageUserSettingsRepository(db)
        self.focus_service = focus_service

        # Register trigger plugins
        self.triggers: list[DeliveryTriggerPlugin] = [
            StaleQueueTrigger(db),
        ]
        if calendar_service:
            self.triggers.append(CalendarEndTrigger(calendar_service))
        # IdleTrigger would be added with Slack integration

    async def check_triggers(self, user_id: str) -> list[DeliveryTrigger]:
        """Check all triggers for a user.

        Returns list of triggers that fired.
        """
        settings = await self.settings_repo.get_by_user_id(user_id)
        if not settings:
            return []

        # Check focus mode interaction
        is_in_focus = False
        if self.focus_service:
            is_in_focus = await self.focus_service.is_in_focus_mode(user_id)

        # Focus-bounded: skip all triggers during focus
        if is_in_focus and settings.product_mode == "focus_bounded":
            return []

        # Always-on: only escalation triggers during focus
        triggers = []
        for trigger_plugin in self.triggers:
            trigger = await trigger_plugin.check(user_id, settings)
            if trigger:
                # Skip non-escalation triggers during focus in always-on mode
                if is_in_focus and trigger.trigger_type != "escalation":
                    continue
                triggers.append(trigger)

        return triggers

    async def deliver_summarize_next(
        self,
        user_id: str,
        trigger: DeliveryTrigger,
    ) -> int:
        """Deliver summarize_next items triggered by a specific event.

        Returns count of items delivered.
        """
        # Get pending summarize_next items
        result = await self.db.execute(
            select(TriageClassification).where(
                and_(
                    TriageClassification.user_id == user_id,
                    TriageClassification.action == "summarize_next",
                    TriageClassification.reviewed_at.is_(None),
                )
            ).order_by(TriageClassification.created_at)
        )
        items = result.scalars().all()

        if not items:
            return 0

        # Build and deliver digest
        # (would call digest_delivery service)
        logger.info(f"Delivering {len(items)} summarize_next items for user {user_id}")

        # Mark as delivered
        for item in items:
            item.reviewed_at = datetime.utcnow()

        await self.db.commit()
        return len(items)

    async def deliver_eod_digest(self, user_id: str) -> int:
        """Deliver end-of-day digest at configured time.

        Called by worker job at user's configured eod_review_time.
        """
        settings = await self.settings_repo.get_by_user_id(user_id)
        if not settings:
            return 0

        # Get summarize_eod items
        result = await self.db.execute(
            select(TriageClassification).where(
                and_(
                    TriageClassification.user_id == user_id,
                    TriageClassification.action == "summarize_eod",
                    TriageClassification.reviewed_at.is_(None),
                )
            ).order_by(TriageClassification.created_at)
        )
        items = result.scalars().all()

        # Build and deliver EOD digest
        logger.info(f"Delivering EOD digest with {len(items)} items for user {user_id}")

        for item in items:
            item.reviewed_at = datetime.utcnow()

        await self.db.commit()
        return len(items)
```

### Step 2: Update worker tasks

- [ ] **Replace digest_scheduler calls**

```python
# backend/app/worker/tasks.py
# Add new scheduled tasks:

@celery_app.task(name="check_delivery_triggers")
def check_delivery_triggers() -> dict:
    """Check delivery triggers for all users with pending items."""
    import asyncio
    from app.core.database import async_session_factory
    from app.services.digest_delivery_orchestrator import DigestDeliveryOrchestrator

    async def _check():
        async with async_session_factory() as db:
            orchestrator = DigestDeliveryOrchestrator(db)
            # Get all users with pending summarize_next items
            # (simplified - would query distinct user_ids)
            triggered = 0
            # for user_id in users_with_pending:
            #     triggers = await orchestrator.check_triggers(user_id)
            #     for trigger in triggers:
            #         await orchestrator.deliver_summarize_next(user_id, trigger)
            #         triggered += 1
            return {"triggered": triggered}

    return asyncio.run(_check())


@celery_app.task(name="deliver_eod_digests")
def deliver_eod_digests() -> dict:
    """Deliver EOD digests for users whose configured time has arrived."""
    import asyncio
    from datetime import datetime
    from app.core.database import async_session_factory
    from app.services.digest_delivery_orchestrator import DigestDeliveryOrchestrator

    async def _deliver():
        async with async_session_factory() as db:
            orchestrator = DigestDeliveryOrchestrator(db)
            # Get current hour:minute in user's timezone
            now = datetime.utcnow()
            current_time = now.strftime("%H:%M")

            # Find users whose eod_review_time matches current time
            # (simplified - would query by time)
            delivered = 0
            # for user_id in users_at_eod_time:
            #     count = await orchestrator.deliver_eod_digest(user_id)
            #     delivered += count
            return {"delivered": delivered}

    return asyncio.run(_deliver())


# Update beat schedule:
celery_app.conf.beat_schedule = {
    # ... existing schedules ...
    "check-delivery-triggers": {
        "task": "check_delivery_triggers",
        "schedule": 60.0,  # Every minute
    },
    "deliver-eod-digests": {
        "task": "deliver_eod_digests",
        "schedule": 60.0,  # Every minute
    },
}
```

### Step 3: Commit

```bash
git add backend/app/services/digest_delivery_orchestrator.py \
        backend/app/worker/tasks.py
git commit -m "feat(triage): create DigestDeliveryOrchestrator with pluggable triggers"
```

---

## Task 3: Implement notify_now auto-degrade

**Files:**
- Modify: `backend/app/services/triage_pipeline.py`
- Modify: `backend/app/worker/tasks.py`

### Step 1: Add auto-degrade worker job

- [ ] **Create degrade task**

```python
# backend/app/worker/tasks.py

@celery_app.task(name="degrade_stale_notify_now")
def degrade_stale_notify_now() -> dict:
    """Degrade notify_now items not engaged with after timeout.

    Default timeout: 4 hours (configurable per user).
    Degrades to summarize_next for inclusion in next digest.
    """
    import asyncio
    from datetime import datetime, timedelta
    from app.core.database import async_session_factory
    from app.db.models.triage import TriageClassification, TriageUserSettings
    from sqlalchemy import select, and_, update

    async def _degrade():
        async with async_session_factory() as db:
            # Get all notify_now items older than default timeout
            default_timeout_hours = 4
            cutoff = datetime.utcnow() - timedelta(hours=default_timeout_hours)

            result = await db.execute(
                select(TriageClassification).where(
                    and_(
                        TriageClassification.action == "notify_now",
                        TriageClassification.created_at < cutoff,
                        TriageClassification.reviewed_at.is_(None),
                    )
                )
            )
            stale = result.scalars().all()

            degraded = 0
            for item in stale:
                # Check user's configured timeout
                # (simplified - would get from TriageUserSettings)
                item.action = "summarize_next"
                item.classification_reason = f"[AUTO-DEGRADED] {item.classification_reason}"
                degraded += 1

            await db.commit()
            return {"degraded": degraded}

    return asyncio.run(_degrade())


# Add to beat schedule:
celery_app.conf.beat_schedule["degrade-stale-notify-now"] = {
    "task": "degrade_stale_notify_now",
    "schedule": 300.0,  # Every 5 minutes
}
```

### Step 2: Commit

```bash
git add backend/app/worker/tasks.py
git commit -m "feat(triage): add notify_now auto-degrade worker job"
```

---

## Task 4: Implement Away Mode

**Files:**
- Create: `backend/app/api/triage_away_mode.py`
- Modify: `backend/app/services/triage_pipeline.py`
- Create: `frontend/src/components/triage/AwayModeToggle.tsx`

### Step 1: Create API endpoints

- [ ] **Create API file**

```python
# backend/app/api/triage_away_mode.py
"""Away mode API for R-AwayMode.

Manual toggle with queue-for-catch-up option.
Catch-up summary delivered when away mode toggles off.
"""

from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.api.deps import get_current_user, get_db
from app.db.models.user import User
from app.db.models.triage import TriageUserSettings
from app.db.repositories.triage import TriageUserSettingsRepository
from app.schemas.triage import TriageSettingsUpdate

router = APIRouter(prefix="/triage/away-mode", tags=["triage-away-mode"])


@router.post("/toggle")
async def toggle_away_mode(
    enabled: bool,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Toggle away mode on/off.

    When toggled off, deliver catch-up digest if items are queued.
    """
    repo = TriageUserSettingsRepository(db)
    settings = await repo.get_by_user_id(current_user.id)

    if not settings:
        raise HTTPException(status_code=404, detail="Settings not found")

    was_enabled = settings.away_mode_enabled
    settings.away_mode_enabled = enabled
    await db.commit()

    # If turning off and items are queued, trigger catch-up
    if was_enabled and not enabled:
        # Check for queued items
        from app.db.models.triage import TriageClassification
        result = await db.execute(
            select(TriageClassification).where(
                TriageClassification.user_id == current_user.id,
                TriageClassification.action == "notify_now",
                # Items queued during away mode would be marked
            )
        )
        queued = result.scalars().all()

        if queued:
            # Trigger catch-up digest delivery
            # (would call delivery orchestrator)
            pass

    return {"away_mode_enabled": enabled}


@router.post("/configure")
async def configure_away_mode(
    notify_now_behavior: str,  # push_immediately | queue_for_catch_up
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Configure away mode behavior for notify_now items."""
    repo = TriageUserSettingsRepository(db)
    settings = await repo.get_by_user_id(current_user.id)

    if not settings:
        raise HTTPException(status_code=404, detail="Settings not found")

    settings.away_mode_notify_now_behavior = notify_now_behavior
    await db.commit()

    return {"notify_now_behavior": notify_now_behavior}
```

### Step 2: Register router

- [ ] **Add to main.py**

```python
# backend/app/main.py

from app.api.triage_away_mode import router as away_mode_router

app.include_router(away_mode_router, prefix="/api")
```

### Step 3: Create frontend toggle

- [ ] **Create component**

```tsx
// frontend/src/components/triage/AwayModeToggle.tsx
import { useState } from 'react'
import { Moon, Sun, Settings } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Switch } from '@/components/ui/switch'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api'

export function AwayModeToggle() {
  const queryClient = useQueryClient()

  const { data: settings } = useQuery({
    queryKey: ['triage', 'settings'],
    queryFn: async () => {
      const { data } = await api.get('/triage/settings')
      return data
    },
  })

  const toggleMutation = useMutation({
    mutationFn: async (enabled: boolean) => {
      await api.post('/triage/away-mode/toggle', null, {
        params: { enabled },
      })
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['triage', 'settings'] })
    },
  })

  const configureMutation = useMutation({
    mutationFn: async (behavior: string) => {
      await api.post('/triage/away-mode/configure', null, {
        params: { notify_now_behavior: behavior },
      })
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['triage', 'settings'] })
    },
  })

  const isEnabled = settings?.away_mode_enabled ?? false

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          {isEnabled ? <Moon className="h-5 w-5" /> : <Sun className="h-5 w-5" />}
          Away Mode
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex items-center justify-between">
          <span className="text-sm">
            Queue messages for catch-up when you return
          </span>
          <Switch
            checked={isEnabled}
            onCheckedChange={(checked) => toggleMutation.mutate(checked)}
          />
        </div>

        {isEnabled && (
          <div className="space-y-2">
            <label className="text-sm font-medium">Notify Now Behavior</label>
            <Select
              value={settings?.away_mode_notify_now_behavior ?? 'push_immediately'}
              onValueChange={(value) => configureMutation.mutate(value)}
            >
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="push_immediately">
                  Push Immediately (default)
                </SelectItem>
                <SelectItem value="queue_for_catch_up">
                  Queue for Catch-Up
                </SelectItem>
              </SelectContent>
            </Select>
          </div>
        )}

        {isEnabled && (
          <p className="text-xs text-muted-foreground">
            Turning off will deliver a catch-up digest with queued messages.
          </p>
        )}
      </CardContent>
    </Card>
  )
}
```

### Step 4: Commit

```bash
git add backend/app/api/triage_away_mode.py \
        backend/app/main.py \
        frontend/src/components/triage/AwayModeToggle.tsx
git commit -m "feat(triage): implement away mode with toggle and configuration"
```

---

## Task 5: Adaptive Delivery Windows (R5c)

**Files:**
- Create: `backend/app/services/adaptive_window_service.py`
- Modify: `backend/app/db/models/triage.py` (add AdaptiveWindow model)
- Create: `frontend/src/components/triage/AdaptiveWindowsCard.tsx`

### Step 1: Create AdaptiveWindow model

- [ ] **Add model**

```python
# backend/app/db/models/triage.py
# Add AdaptiveWindow model:

class AdaptiveWindow(Base, UUIDMixin, TimestampMixin):
    """Per-(user, message_type) adaptive delivery window.

    Windows adapt based on engagement patterns.
    EMA update with α=0.2, 30-day half-life decay.
    """

    __tablename__ = "adaptive_windows"

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    message_type_id: Mapped[str] = mapped_column(
        ForeignKey("message_types.id"), nullable=False
    )
    window_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    sample_count: Mapped[int] = mapped_column(Integer, default=0)
    last_updated: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    user: Mapped["User"] = relationship("User")
    message_type: Mapped["MessageType"] = relationship("MessageType")

    __table_args__ = (
        {"comment": "UNIQUE(user_id, message_type_id)"},
    )
```

### Step 2: Create service

- [ ] **Create service file**

```python
# backend/app/services/adaptive_window_service.py
"""Adaptive delivery window management (R5c).

Starter values:
- pr_review_request: 30 min
- direct_question: 30 min
- mention: 30 min
- discussion_relevant: 60 min
- announcement: end-of-day
- informational: end-of-day

Adaptive learning:
- EMA with α=0.2
- Per-type floor and ceiling
- Min 5 samples before adjustment
- Damping: single engagement cannot shift by >50%
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.triage import AdaptiveWindow, MessageType

logger = logging.getLogger(__name__)

EMA_ALPHA = 0.2
MIN_SAMPLES = 5
MAX_SHIFT_FRACTION = 0.5

STARTER_WINDOWS = {
    "pr_review_request": 30,
    "direct_question": 30,
    "mention": 30,
    "discussion_relevant_to_my_work": 60,
    "announcement": 1440,  # end-of-day (24 hours in minutes)
    "informational": 1440,
}


@dataclass
class WindowConfig:
    """Adaptive window configuration."""
    message_type: str
    window_minutes: int
    sample_count: int
    is_learning: bool  # True if sample_count < MIN_SAMPLES


class AdaptiveWindowService:
    """Manages adaptive delivery windows per message type."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_window(
        self,
        user_id: str,
        message_type_name: str,
    ) -> WindowConfig:
        """Get current window for a message type.

        Returns starter value if no learned data exists.
        """
        # Get message type
        result = await self.db.execute(
            select(MessageType).where(
                MessageType.user_id == user_id,
                MessageType.type_name == message_type_name,
            )
        )
        msg_type = result.scalar_one_or_none()

        if not msg_type:
            # Return default
            return WindowConfig(
                message_type=message_type_name,
                window_minutes=STARTER_WINDOWS.get(message_type_name, 60),
                sample_count=0,
                is_learning=True,
            )

        # Get adaptive window
        result = await self.db.execute(
            select(AdaptiveWindow).where(
                AdaptiveWindow.user_id == user_id,
                AdaptiveWindow.message_type_id == msg_type.id,
            )
        )
        window = result.scalar_one_or_none()

        if not window:
            return WindowConfig(
                message_type=message_type_name,
                window_minutes=STARTER_WINDOWS.get(message_type_name, 60),
                sample_count=0,
                is_learning=True,
            )

        return WindowConfig(
            message_type=message_type_name,
            window_minutes=window.window_minutes,
            sample_count=window.sample_count,
            is_learning=window.sample_count < MIN_SAMPLES,
        )

    async def record_engagement(
        self,
        user_id: str,
        message_type_name: str,
        actual_delay_minutes: int,
    ) -> None:
        """Record an engagement and update window if threshold met.

        Uses EMA update with damping to prevent oscillation.
        """
        # Get or create adaptive window
        result = await self.db.execute(
            select(MessageType).where(
                MessageType.user_id == user_id,
                MessageType.type_name == message_type_name,
            )
        )
        msg_type = result.scalar_one_or_none()

        if not msg_type:
            return

        result = await self.db.execute(
            select(AdaptiveWindow).where(
                AdaptiveWindow.user_id == user_id,
                AdaptiveWindow.message_type_id == msg_type.id,
            )
        )
        window = result.scalar_one_or_none()

        if not window:
            starter = STARTER_WINDOWS.get(message_type_name, 60)
            window = AdaptiveWindow(
                user_id=user_id,
                message_type_id=msg_type.id,
                window_minutes=starter,
            )
            self.db.add(window)

        window.sample_count += 1

        # Only update if minimum samples met
        if window.sample_count >= MIN_SAMPLES:
            old_window = window.window_minutes
            new_window = old_window * (1 - EMA_ALPHA) + actual_delay_minutes * EMA_ALPHA

            # Apply damping: max 50% shift
            max_shift = old_window * MAX_SHIFT_FRACTION
            if abs(new_window - old_window) > max_shift:
                if new_window > old_window:
                    new_window = old_window + max_shift
                else:
                    new_window = old_window - max_shift

            # Apply bounds (floor: 15 min, ceiling: 1440 min)
            new_window = max(15, min(1440, int(new_window)))

            window.window_minutes = new_window
            logger.info(
                f"Updated window for {message_type_name}: "
                f"{old_window} → {new_window} min (sample #{window.sample_count})"
            )

        window.last_updated = datetime.utcnow()
        await self.db.commit()

    async def reset_window(
        self,
        user_id: str,
        message_type_name: str,
    ) -> None:
        """Reset window to starter value."""
        result = await self.db.execute(
            select(MessageType).where(
                MessageType.user_id == user_id,
                MessageType.type_name == message_type_name,
            )
        )
        msg_type = result.scalar_one_or_none()

        if not msg_type:
            return

        result = await self.db.execute(
            select(AdaptiveWindow).where(
                AdaptiveWindow.user_id == user_id,
                AdaptiveWindow.message_type_id == msg_type.id,
            )
        )
        window = result.scalar_one_or_none()

        if window:
            window.window_minutes = STARTER_WINDOWS.get(message_type_name, 60)
            window.sample_count = 0
            window.last_updated = datetime.utcnow()
            await self.db.commit()
```

### Step 3: Create frontend card

- [ ] **Create component**

```tsx
// frontend/src/components/triage/AdaptiveWindowsCard.tsx
import { Clock, RotateCcw } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api'

interface AdaptiveWindow {
  message_type: string
  window_minutes: number
  sample_count: number
  is_learning: boolean
}

export function AdaptiveWindowsCard() {
  const queryClient = useQueryClient()

  const { data: windows, isLoading } = useQuery({
    queryKey: ['triage', 'adaptive-windows'],
    queryFn: async () => {
      const { data } = await api.get<AdaptiveWindow[]>('/triage/adaptive-windows')
      return data
    },
  })

  const resetMutation = useMutation({
    mutationFn: async (messageType: string) => {
      await api.post(`/triage/adaptive-windows/${messageType}/reset`)
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['triage', 'adaptive-windows'] })
    },
  })

  if (isLoading) return <div>Loading...</div>
  if (!windows?.length) return null

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Clock className="h-5 w-5" />
          Delivery Windows
        </CardTitle>
      </CardHeader>
      <CardContent>
        <p className="text-sm text-muted-foreground mb-4">
          Windows adapt based on when you engage with different message types.
        </p>

        <div className="space-y-3">
          {windows.map((w) => (
            <div key={w.message_type} className="flex items-center justify-between">
              <div>
                <div className="font-medium">{w.message_type}</div>
                <div className="text-sm text-muted-foreground">
                  {w.is_learning ? (
                    <span className="text-yellow-600">Still learning ({w.sample_count}/5 samples)</span>
                  ) : (
                    <span>{w.window_minutes} min window</span>
                  )}
                </div>
              </div>
              {!w.is_learning && (
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => resetMutation.mutate(w.message_type)}
                >
                  <RotateCcw className="h-4 w-4" />
                </Button>
              )}
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  )
}
```

### Step 4: Commit

```bash
git add backend/app/services/adaptive_window_service.py \
        backend/app/db/models/triage.py \
        frontend/src/components/triage/AdaptiveWindowsCard.tsx
git commit -m "feat(triage): implement adaptive delivery windows with EMA learning"
```

---

## Acceptance Criteria Checklist

- [ ] No clock-interval delivery for summarize_next except per-type backstop
- [ ] Calendar integration wired into delivery triggers
- [ ] Engagement check gates notify_now
- [ ] Focus mode suppresses non-escalation deliveries in both product modes
- [ ] Per-type windows configurable with adaptive learning
- [ ] Per-type window UI surfaces current value, reasoning, "still learning" framing
- [ ] notify_now auto-degrade after configurable timeout
- [ ] Manual away mode toggle exists
- [ ] User can configure notify_now behavior while away
- [ ] Queued items deliverable as single catch-up digest on toggle off
- [ ] Data model supports calendar-driven activation when added later

---

## Phase 4 Complete!

All four phases of the Alfred Triage v3.2 implementation are now planned.

**Total Estimated Duration:** 10-11 weeks

**Deployment Strategy:**
1. Deploy Phase 1 → Monitor R-Cache size and engagement check metrics
2. Deploy Phase 2 → Gather learning signal effectiveness data
3. Deploy Phase 3 → Validate bot rules and escalation patterns
4. Deploy Phase 4 → Fine-tune adaptive windows and delivery triggers

**Key Metrics to Track:**
- Classification recall (target: ≥90%)
- Delivery hit rate (target: ≥80%)
- R-Cache size and cleanup success
- Slack API rate limit fallback frequency

---

*End of Phase 4 plan. Return to 00-overview.md for summary.*
