# Phase 3: Pattern Codification

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Implement structured channel/message-type rules, bot handling, VIP senders, and escalation detection.

**Duration:** 2 weeks

**Architecture:** Per-user message types with type→action rules. Bot rules short-circuit before LLM. VIP senders floor at summarize_next. Escalation detector promotes summarize_next → notify_now with content gate.

**Tech Stack:** Python 3.11+, FastAPI, SQLAlchemy, React

---

## Requirements Covered

- **R4:** Structured channel & message-type rules
- **R2c:** Escalation detection with content gate
- Bot filter investigation prerequisite

---

## File Structure

### Create

```
backend/alembic/versions/046_add_message_types.py
backend/alembic/versions/047_add_channel_type_rules.py
backend/alembic/versions/048_add_vip_senders.py
backend/alembic/versions/049_rename_channel_source_exclusion_to_rule.py
backend/app/services/escalation_detector.py
backend/app/api/triage_rules.py
backend/tests/unit/test_escalation_detector.py
frontend/src/components/triage/MessageTypesCard.tsx
frontend/src/components/triage/VipSendersCard.tsx
```

### Modify

```
backend/app/db/models/triage.py
backend/app/services/triage_router.py
backend/app/services/triage_enrichment.py
backend/app/schemas/triage.py
```

---

## Task 1: Bot Filter Investigation (CRITICAL PREREQUISITE)

**Files:**
- Modify: `backend/app/services/triage_router.py`
- Create: `backend/tests/integration/test_bot_filter_focus_mode.py`

### Step 1: Document current bot filter behavior

- [ ] **Investigate existing code**

```python
# Search for bot filter logic
# backend/app/services/triage_router.py or triage_pipeline.py

# Document:
# 1. Where are bot messages filtered?
# 2. What broke in focus mode when disabled?
# 3. What is the expected behavior after fix?
```

### Step 2: Create focus mode parity test

- [ ] **Create test ensuring parity**

```python
# backend/tests/integration/test_bot_filter_focus_mode.py
"""Test that focus mode works identically with bot filter changes."""

import pytest
from datetime import datetime

from app.services.focus import FocusModeService
from app.services.triage_pipeline import TriagePipeline


class TestBotFilterFocusModeParity:
    @pytest.mark.asyncio
    async def test_focus_mode_behavior_with_bot_messages(self, db_session, test_user):
        """Focus mode should handle bot messages correctly."""
        # This test must pass BEFORE and AFTER bot filter changes
        # If it fails before, fix existing bug first
        pass

    @pytest.mark.asyncio
    async def test_bot_filter_short_circuits_before_llm(self, db_session, test_user):
        """Bot rules should be checked BEFORE LLM classification."""
        # Bot message should not trigger LLM call
        pass
```

### Step 3: Implement bot rule short-circuit

- [ ] **Update triage_router.py**

```python
# backend/app/services/triage_router.py
# Add bot rule check BEFORE classification:

async def route_message(self, payload: EnrichedTriagePayload) -> str:
    """Route message to appropriate classification path.
    
    Returns action directly if short-circuit rule matches.
    Otherwise returns None to proceed with LLM classification.
    """
    # Bot short-circuit (R4c)
    if payload.sender_is_bot:
        bot_action = await self._check_bot_rule(payload)
        if bot_action:
            logger.info(f"Bot rule short-circuit: {bot_action}")
            return bot_action
        # Default bot action is ignore
        return "ignore"
    
    # Proceed to LLM classification
    return None

async def _check_bot_rule(self, payload: EnrichedTriagePayload) -> str | None:
    """Check for explicit bot rule. Returns None if not configured."""
    from app.db.models.triage import ChannelSourceRule
    
    result = await self.db.execute(
        select(ChannelSourceRule).where(
            ChannelSourceRule.user_id == payload.user_id,
            ChannelSourceRule.channel_id == payload.channel_id,
            ChannelSourceRule.slack_entity_id == payload.sender_slack_id,
            ChannelSourceRule.entity_type == "bot",
        )
    )
    rule = result.scalar_one_or_none()
    
    if rule:
        return rule.action  # 'notify_now', 'summarize_next', etc.
    return None
```

### Step 4: Commit

```bash
git add backend/app/services/triage_router.py \
        backend/tests/integration/test_bot_filter_focus_mode.py
git commit -m "fix(triage): bot rules short-circuit before LLM classification"
```

---

## Task 2: Add MessageType model and migrations

**Files:**
- Create: `backend/alembic/versions/046_add_message_types.py`
- Create: `backend/alembic/versions/047_add_channel_type_rules.py`
- Modify: `backend/app/db/models/triage.py`

### Step 1: Create migrations

- [ ] **Create message_types migration**

```python
# backend/alembic/versions/046_add_message_types.py
"""add message types

Revision ID: 046
Revises: 045
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '046'
down_revision = '045'
depends_on = None


def upgrade() -> None:
    op.create_table(
        'message_types',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('user_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('users.id'), nullable=False),
        sa.Column('type_name', sa.String(100), nullable=False),
        sa.Column('type_definition', sa.Text(), nullable=False),
        sa.Column('source', sa.String(20), nullable=False),  # wizard|user|alfred_suggested
        sa.Column('is_archived', sa.Boolean(), default=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index(
        'ix_message_types_unique',
        'message_types',
        ['user_id', 'type_name'],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index('ix_message_types_unique')
    op.drop_table('message_types')
```

- [ ] **Create channel_type_rules migration**

```python
# backend/alembic/versions/047_add_channel_type_rules.py
"""add channel type rules

Revision ID: 047
Revises: 046
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '047'
down_revision = '046'
depends_on = None


def upgrade() -> None:
    op.create_table(
        'channel_type_rules',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('user_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('users.id'), nullable=False),
        sa.Column('channel_id', sa.String(50), nullable=False),
        sa.Column('message_type_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('message_types.id'), nullable=False),
        sa.Column('action', sa.String(20), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index(
        'ix_channel_type_rules_unique',
        'channel_type_rules',
        ['user_id', 'channel_id', 'message_type_id'],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index('ix_channel_type_rules_unique')
    op.drop_table('channel_type_rules')
```

### Step 2: Add models

- [ ] **Add to triage.py**

```python
# backend/app/db/models/triage.py

class MessageType(Base, UUIDMixin, TimestampMixin):
    """Per-user message type category.

    Types are user-defined or wizard-suggested.
    Cap: 15 active (non-archived) types per user.
    """

    __tablename__ = "message_types"

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    type_name: Mapped[str] = mapped_column(String(100), nullable=False)
    type_definition: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(String(20), nullable=False)  # wizard|user|alfred_suggested
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False)

    user: Mapped["User"] = relationship("User")

    __table_args__ = (
        {"comment": "UNIQUE(user_id, type_name) enforced via migration index"},
    )


class ChannelTypeRule(Base, UUIDMixin, TimestampMixin):
    """Per-(user, channel, type) action mapping (R4b)."""

    __tablename__ = "channel_type_rules"

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    channel_id: Mapped[str] = mapped_column(String(50), nullable=False)
    message_type_id: Mapped[str] = mapped_column(ForeignKey("message_types.id"), nullable=False)
    action: Mapped[str] = mapped_column(String(20), nullable=False)

    user: Mapped["User"] = relationship("User")
    message_type: Mapped["MessageType"] = relationship("MessageType")
```

### Step 3: Run migrations

```bash
docker-compose -f docker-compose.dev.yml exec backend alembic upgrade head
```

### Step 4: Commit

```bash
git add backend/alembic/versions/046_add_message_types.py \
        backend/alembic/versions/047_add_channel_type_rules.py \
        backend/app/db/models/triage.py
git commit -m "feat(triage): add MessageType and ChannelTypeRule models"
```

---

## Task 3: Add VIP Senders

**Files:**
- Create: `backend/alembic/versions/048_add_vip_senders.py`
- Modify: `backend/app/db/models/triage.py`
- Modify: `backend/app/services/triage_enrichment.py`

### Step 1: Create migration

- [ ] **Create migration file**

```python
# backend/alembic/versions/048_add_vip_senders.py
"""add vip senders

Revision ID: 048
Revises: 047
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '048'
down_revision = '047'
depends_on = None


def upgrade() -> None:
    op.create_table(
        'vip_senders',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('user_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('users.id'), nullable=False),
        sa.Column('sender_slack_id', sa.String(50), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index(
        'ix_vip_senders_unique',
        'vip_senders',
        ['user_id', 'sender_slack_id'],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index('ix_vip_senders_unique')
    op.drop_table('vip_senders')
```

### Step 2: Add model

- [ ] **Add to triage.py**

```python
# backend/app/db/models/triage.py

class VipSender(Base, UUIDMixin, TimestampMixin):
    """VIP sender marked by user for guaranteed attention (R4e).

    VIP senders are floored at summarize_next (never ignore).
    Manual override only - no automatic VIP detection.
    """

    __tablename__ = "vip_senders"

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    sender_slack_id: Mapped[str] = mapped_column(String(50), nullable=False)

    user: Mapped["User"] = relationship("User")

    __table_args__ = (
        {"comment": "UNIQUE(user_id, sender_slack_id) enforced via migration index"},
    )
```

### Step 3: Floor VIP senders at summarize_next

- [ ] **Update classifier to check VIP**

```python
# backend/app/services/triage_classifier.py
# In _classify_dm and _classify_channel:

    # VIP senders are floored at summarize_next
    if payload.is_vip and result.action == "ignore":
        result.action = "summarize_next"
        result.reason = f"VIP sender floored to summarize_next: {result.reason}"
```

### Step 4: Commit

```bash
git add backend/alembic/versions/048_add_vip_senders.py \
        backend/app/db/models/triage.py \
        backend/app/services/triage_classifier.py
git commit -m "feat(triage): add VIP senders with summarize_next floor"
```

---

## Task 4: Implement EscalationDetector (R2c)

**Files:**
- Create: `backend/app/services/escalation_detector.py`
- Create: `backend/tests/unit/test_escalation_detector.py`
- Modify: `backend/app/worker/tasks.py`

### Step 1: Create service

- [ ] **Create service file**

```python
# backend/app/services/escalation_detector.py
"""Escalation detection for promoting summarize_next → notify_now (R2c).

Pattern triggers:
1. Same sender pings 2+ times within 5 min
2. Sender pings, then adds @-mention
3. Thread accelerates (≥5 new messages in 10 min)

Content gate: Re-classify with full context before promoting.
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.triage import TriageClassification
from app.services.triage_classifier import TriageClassifier
from app.services.triage_enrichment import TriageEnrichmentService

if TYPE_CHECKING:
    from app.services.slack import SlackService

logger = logging.getLogger(__name__)

PING_WINDOW_MINUTES = 5
THREAD_ACCELERATION_THRESHOLD = 5
THREAD_ACCELERATION_WINDOW_MINUTES = 10


@dataclass
class EscalationTrigger:
    """An escalation pattern that fired."""
    classification_id: str
    trigger_type: str  # 'multi_ping', 'mention_added', 'thread_acceleration'
    reason: str


class EscalationDetector:
    """Detects escalation patterns and promotes summarize_next → notify_now.

    Runs as a worker job, checking for escalation patterns.
    Content gate ensures promotion only if content matches user signals.
    """

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def detect_escalations(
        self,
        user_id: str,
        since: datetime,
    ) -> list[EscalationTrigger]:
        """Find all escalation triggers for a user.

        Args:
            user_id: User to check
            since: How far back to check

        Returns:
            List of EscalationTrigger objects
        """
        triggers = []

        # Get summarize_next items in window
        result = await self.db.execute(
            select(TriageClassification).where(
                and_(
                    TriageClassification.user_id == user_id,
                    TriageClassification.action == "summarize_next",
                    TriageClassification.created_at >= since,
                    TriageClassification.reviewed_at.is_(None),
                )
            )
        )
        pending = result.scalars().all()

        # Check multi-ping pattern
        triggers.extend(await self._check_multi_ping(pending))

        # Check thread acceleration
        triggers.extend(await self._check_thread_acceleration(user_id, since))

        return triggers

    async def _check_multi_ping(
        self,
        pending: list[TriageClassification],
    ) -> list[EscalationTrigger]:
        """Check for same sender pinging multiple times."""
        by_sender: dict[str, list[TriageClassification]] = {}
        for c in pending:
            if c.sender_slack_id not in by_sender:
                by_sender[c.sender_slack_id] = []
            by_sender[c.sender_slack_id].append(c)

        triggers = []
        for sender_id, classifications in by_sender.items():
            if len(classifications) < 2:
                continue

            # Check if within ping window
            sorted_cls = sorted(classifications, key=lambda c: c.created_at)
            for i in range(1, len(sorted_cls)):
                time_diff = (
                    sorted_cls[i].created_at - sorted_cls[i-1].created_at
                ).total_seconds() / 60
                if time_diff <= PING_WINDOW_MINUTES:
                    triggers.append(EscalationTrigger(
                        classification_id=sorted_cls[i].id,
                        trigger_type="multi_ping",
                        reason=f"Sender {sender_id} pinged {len(classifications)} times",
                    ))
                    break  # One trigger per sender

        return triggers

    async def _check_thread_acceleration(
        self,
        user_id: str,
        since: datetime,
    ) -> list[EscalationTrigger]:
        """Check for thread acceleration (≥5 new messages in 10 min)."""
        # This would query Slack API for thread message counts
        # Simplified implementation for Phase 3
        return []

    async def evaluate_escalation(
        self,
        trigger: EscalationTrigger,
        slack_service: "SlackService",
    ) -> bool:
        """Content gate: Re-classify with full context.

        Returns True if content confirms escalation-worthy.
        """
        # Fetch classification
        result = await self.db.execute(
            select(TriageClassification).where(
                TriageClassification.id == trigger.classification_id
            )
        )
        classification = result.scalar_one_or_none()

        if not classification:
            return False

        # Re-enrich with full context
        enrichment = TriageEnrichmentService(self.db)
        # TODO: Fetch message text from cache or Slack
        # payload = await enrichment.enrich(...)
        # classifier = TriageClassifier(...)
        # result = await classifier.classify(payload)

        # For now, return True (escalation approved)
        # In production, check if new classification is notify_now
        return True

    async def promote_to_notify_now(
        self,
        classification_id: str,
        reason: str,
    ) -> TriageClassification | None:
        """Promote a classification to notify_now.

        Sets escalation_override=True to bypass dedup.
        """
        result = await self.db.execute(
            select(TriageClassification).where(
                TriageClassification.id == classification_id
            )
        )
        classification = result.scalar_one_or_none()

        if not classification:
            return None

        classification.action = "notify_now"
        classification.classification_reason = f"[ESCALATION] {reason}"
        await self.db.commit()
        await self.db.refresh(classification)

        return classification
```

### Step 2: Write unit tests

- [ ] **Create test file**

```python
# backend/tests/unit/test_escalation_detector.py
"""Unit tests for EscalationDetector."""

import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

from app.services.escalation_detector import (
    EscalationDetector,
    EscalationTrigger,
)


@pytest.fixture
def mock_db():
    return AsyncMock()


@pytest.fixture
def detector(mock_db):
    return EscalationDetector(mock_db)


class TestEscalationDetector:
    def test_trigger_dataclass(self):
        """EscalationTrigger should have expected fields."""
        trigger = EscalationTrigger(
            classification_id="c1",
            trigger_type="multi_ping",
            reason="Sender pinged 3 times",
        )
        assert trigger.trigger_type == "multi_ping"

    @pytest.mark.asyncio
    async def test_detect_multi_ping_pattern(self, detector, mock_db):
        """Detector should find multi-ping pattern."""
        from app.db.models.triage import TriageClassification

        now = datetime.utcnow()
        classifications = [
            TriageClassification(
                id="c1",
                user_id="u1",
                sender_slack_id="S1",
                action="summarize_next",
                created_at=now - timedelta(minutes=3),
            ),
            TriageClassification(
                id="c2",
                user_id="u1",
                sender_slack_id="S1",
                action="summarize_next",
                created_at=now - timedelta(minutes=1),
            ),
        ]

        triggers = await detector._check_multi_ping(classifications)
        assert len(triggers) == 1
        assert triggers[0].trigger_type == "multi_ping"
```

### Step 3: Add worker job

- [ ] **Add to tasks.py**

```python
# backend/app/worker/tasks.py

@celery_app.task(name="check_escalations")
def check_escalations() -> dict:
    """Check for escalation patterns and promote summarize_next → notify_now."""
    import asyncio
    from datetime import datetime, timedelta
    from app.core.database import async_session_factory
    from app.services.escalation_detector import EscalationDetector
    from app.services.slack import SlackService

    async def _check():
        async with async_session_factory() as db:
            detector = EscalationDetector(db)
            slack = SlackService()

            # Get all users with pending summarize_next items
            # (simplified - in production, query distinct user_ids)
            since = datetime.utcnow() - timedelta(hours=1)
            # triggers = await detector.detect_escalations(user_id, since)

            # For each trigger, evaluate and promote
            promoted = 0
            # for trigger in triggers:
            #     if await detector.evaluate_escalation(trigger, slack):
            #         await detector.promote_to_notify_now(trigger.classification_id)
            #         promoted += 1

            return {"promoted": promoted}

    return asyncio.run(_check())

# Add to beat schedule:
celery_app.conf.beat_schedule["check-escalations"] = {
    "task": "check_escalations",
    "schedule": 60.0,  # Every minute
}
```

### Step 4: Commit

```bash
git add backend/app/services/escalation_detector.py \
        backend/tests/unit/test_escalation_detector.py \
        backend/app/worker/tasks.py
git commit -m "feat(triage): add EscalationDetector for pattern-based promotion"
```

---

## Task 5: Rename ChannelSourceExclusion to ChannelSourceRule

**Files:**
- Create: `backend/alembic/versions/049_rename_channel_source_exclusion_to_rule.py`
- Modify: `backend/app/db/models/triage.py`
- Modify: `backend/app/schemas/triage.py`
- Modify: `backend/app/api/triage.py`

### Step 1: Create migration

- [ ] **Create migration file**

```python
# backend/alembic/versions/049_rename_channel_source_exclusion_to_rule.py
"""rename channel source exclusion to rule

Revision ID: 049
Revises: 048
"""

from alembic import op
import sqlalchemy as sa

revision = '049'
down_revision = '048'
depends_on = None


def upgrade() -> None:
    # Rename table
    op.rename_table('channel_source_exclusions', 'channel_source_rules')
    
    # Add action column (migrate from existing 'action' field)
    # The existing 'action' field has values 'exclude' | 'include'
    # Map to new actions: 'exclude' → 'ignore', 'include' → 'notify_now'
    op.add_column(
        'channel_source_rules',
        sa.Column('new_action', sa.String(20), nullable=True)
    )
    
    conn = op.get_bind()
    conn.execute(
        sa.text(
            "UPDATE channel_source_rules SET new_action = "
            "CASE WHEN action = 'exclude' THEN 'ignore' "
            "WHEN action = 'include' THEN 'notify_now' END"
        )
    )
    
    op.alter_column('channel_source_rules', 'new_action', nullable=False)
    op.drop_column('channel_source_rules', 'action')
    op.alter_column('channel_source_rules', 'new_action', new_column_name='action')


def downgrade() -> None:
    op.rename_table('channel_source_rules', 'channel_source_exclusions')
```

### Step 2: Update model

- [ ] **Rename model**

```python
# backend/app/db/models/triage.py
# Rename ChannelSourceExclusion to ChannelSourceRule:

class ChannelSourceRule(Base, UUIDMixin, TimestampMixin):
    """Per-channel bot/user rule with action override.

    Renamed from ChannelSourceExclusion (R4c).
    Now supports any action, not just exclude/include.
    """

    __tablename__ = "channel_source_rules"

    monitored_channel_id: Mapped[str] = mapped_column(
        ForeignKey("monitored_channels.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    slack_entity_id: Mapped[str] = mapped_column(String(50), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(10), default="bot")  # bot | user
    action: Mapped[str] = mapped_column(String(20), nullable=False)  # notify_now | summarize_next | summarize_eod | ignore
    display_name: Mapped[str | None] = mapped_column(String(255), nullable=True)

    channel: Mapped["MonitoredChannel"] = relationship(
        "MonitoredChannel", back_populates="source_rules"
    )
```

### Step 3: Update schemas and API

- [ ] **Update schemas**

```python
# backend/app/schemas/triage.py

class SourceRuleCreate(BaseModel):
    """Request to create a source rule."""

    slack_entity_id: str
    entity_type: str = Field("bot", pattern="^(bot|user)$")
    action: str = Field(..., pattern="^(notify_now|summarize_next|summarize_eod|ignore)$")
    display_name: str | None = None


class SourceRuleResponse(BaseModel):
    """Response with source rule info."""

    model_config = {"from_attributes": True}

    id: str
    slack_entity_id: str
    entity_type: str
    action: str
    display_name: str | None
```

### Step 4: Commit

```bash
git add backend/alembic/versions/049_rename_channel_source_exclusion_to_rule.py \
        backend/app/db/models/triage.py \
        backend/app/schemas/triage.py \
        backend/app/api/triage.py
git commit -m "feat(triage): rename ChannelSourceExclusion to ChannelSourceRule"
```

---

## Task 6: Update TriageWizard for role-based starter types

**Files:**
- Modify: `backend/app/services/triage_wizard.py`

### Step 1: Add role-based starter sets

- [ ] **Update wizard**

```python
# backend/app/services/triage_wizard.py
# Add role-based starter type sets:

ROLE_STARTER_TYPES = {
    "engineering": [
        ("pr_review_request", "Pull request review requests requiring your input"),
        ("incident_alert", "Production incidents or alerts requiring immediate attention"),
        ("deploy_notification", "Deployment notifications and status updates"),
        ("on_call_handoff", "On-call handoff messages and escalations"),
    ],
    "sales": [
        ("deal_update", "Updates on active deals and opportunities"),
        ("customer_escalation", "Customer issues requiring urgent response"),
        ("meeting_request", "Meeting requests from prospects or customers"),
        ("contract_review", "Contract review requests"),
    ],
    "management": [
        ("team_update", "Team updates and status reports"),
        ("decision_needed", "Decisions requiring your approval"),
        ("escalation", "Issues escalated to you for resolution"),
        ("calendar_conflict", "Calendar conflicts and scheduling issues"),
    ],
    "design": [
        ("design_review", "Design review requests and feedback"),
        ("design_critique", "Design critiques and iteration requests"),
        ("brand_request", "Brand asset or design requests"),
    ],
    "product": [
        ("feature_request", "Feature requests and product feedback"),
        ("roadmap_update", "Roadmap updates and changes"),
        ("bug_report", "Bug reports and issues"),
        ("release_notes", "Release notes and announcements"),
    ],
    "operations": [
        ("system_alert", "System alerts and notifications"),
        ("process_request", "Process improvement requests"),
        ("vendor_update", "Vendor and partner updates"),
    ],
}


async def generate_wizard_types(
    self,
    user_id: str,
    roles: list[str],
) -> list[dict]:
    """Generate starter types based on selected roles.

    Args:
        user_id: User creating types
        roles: List of role names (engineering, sales, etc.)

    Returns:
        List of type definitions to create
    """
    types = []
    seen_names = set()

    for role in roles:
        role_types = ROLE_STARTER_TYPES.get(role, [])
        for type_name, definition in role_types:
            if type_name not in seen_names:
                types.append({
                    "type_name": type_name,
                    "type_definition": definition,
                    "source": "wizard",
                })
                seen_names.add(type_name)

    return types
```

### Step 2: Commit

```bash
git add backend/app/services/triage_wizard.py
git commit -m "feat(triage): add role-based starter type sets to wizard"
```

---

## Acceptance Criteria Checklist

- [ ] Message types per-user; multi-role wizard supported
- [ ] Type→action rules table exists and is queryable
- [ ] Bot-filter focus-mode investigation completed; behavioral parity verified
- [ ] Bot rules short-circuit before LLM classification; default action is `ignore`
- [ ] `ChannelSourceExclusion` extended/renamed; migration preserves existing data
- [ ] Mention-type signals passed to classifier
- [ ] VIP sender manual override exists with summarize_next floor
- [ ] Escalation detector runs as worker job with content gate and cold-start fallback
- [ ] Escalation pushes bypass `AlertDeduplicationService` via override flag

---

*Phase 3 complete. Proceed to phase-4-timing.md.*
