# Plan 3: Delivery Checker + Digest Subagent

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a delivery checker that uses settle/TTL logic to determine when P1 messages are ready, and a digest subagent that holistically groups, summarizes, and delivers messages via Slack DM.

**Architecture:** A lightweight periodic worker (every 2-3 min) checks P1 message groups for settle/TTL readiness and triggers EOD digests at the user's configured time. When messages are ready, it dispatches a LangGraph digest subagent that reviews all ready messages, groups related conversations, fetches additional context, generates summaries, and delivers via Slack DM. The subagent replaces the current `send_digest` task's deterministic grouping + LLM summarization.

**Tech Stack:** Python 3.11+, LangGraph, Vertex AI (Gemini), SQLAlchemy 2.0, Redis, Slack API, ARQ

**Spec:** `docs/superpowers/specs/2026-05-31-agent-driven-triage-design.md`

---

## File Structure

### New Files
- `backend/app/services/delivery_checker.py` — Settle/TTL delivery readiness checker
- `backend/app/agents/digest/__init__.py`
- `backend/app/agents/digest/state.py` — DigestAgentState TypedDict
- `backend/app/agents/digest/prompt.py` — Digest subagent system prompt
- `backend/app/agents/digest/graph.py` — StateGraph construction
- `backend/app/agents/digest/nodes.py` — Node functions
- `backend/app/agents/digest/agent.py` — DigestAgent class
- `backend/app/agents/digest/tools/__init__.py` — Tool registry
- `backend/app/agents/digest/tools/fetch_thread.py` — Fetch thread for summarization
- `backend/app/agents/digest/tools/fetch_channel_history.py` — Fetch channel context
- `backend/app/agents/digest/tools/send_digest_dm.py` — Send formatted Slack DM
- `backend/app/agents/digest/tools/save_digest_record.py` — Persist digest to DB
- `backend/app/agents/digest/tools/mark_delivered.py` — Update message statuses
- `backend/tests/services/test_delivery_checker.py`
- `backend/tests/agents/digest/test_digest_agent.py`
- `backend/tests/agents/digest/test_digest_tools.py`

### Modified Files
- `backend/app/worker/tasks.py` — Add `check_delivery_readiness` and `run_digest_agent` tasks
- `backend/app/worker/main.py` — Register new tasks, add cron job for delivery checker

---

## Task 1: Delivery Checker Service

**Files:**
- Create: `backend/app/services/delivery_checker.py`
- Create: `backend/tests/services/test_delivery_checker.py`

- [ ] **Step 1: Write tests**

Create `backend/tests/services/test_delivery_checker.py`:

```python
"""Tests for delivery checker service."""

import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.delivery_checker import DeliveryChecker


@pytest.fixture
def mock_db():
    return AsyncMock()


@pytest.fixture
def checker(mock_db):
    return DeliveryChecker(mock_db)


class TestGetReadyP1Groups:
    @pytest.mark.asyncio
    async def test_settled_group_is_ready(self, checker, mock_db):
        """Group with no activity past settled_threshold should be ready."""
        now = datetime.now(timezone.utc)
        mock_item = MagicMock()
        mock_item.user_id = "user1"
        mock_item.group_id = "group1"
        mock_item.deliver_by = now + timedelta(hours=1)
        mock_item.settled_threshold = 30
        mock_item.last_related_activity_at = now - timedelta(minutes=35)  # settled

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_item]
        mock_db.execute = AsyncMock(return_value=mock_result)

        ready = await checker.get_ready_p1_groups("user1")
        assert len(ready) == 1

    @pytest.mark.asyncio
    async def test_expired_ttl_is_ready(self, checker, mock_db):
        """Group past deliver_by deadline should be ready."""
        now = datetime.now(timezone.utc)
        mock_item = MagicMock()
        mock_item.user_id = "user1"
        mock_item.group_id = "group1"
        mock_item.deliver_by = now - timedelta(minutes=5)  # expired
        mock_item.settled_threshold = 30
        mock_item.last_related_activity_at = now - timedelta(minutes=10)

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_item]
        mock_db.execute = AsyncMock(return_value=mock_result)

        ready = await checker.get_ready_p1_groups("user1")
        assert len(ready) == 1

    @pytest.mark.asyncio
    async def test_active_group_not_ready(self, checker, mock_db):
        """Group with recent activity and future TTL should not be ready."""
        now = datetime.now(timezone.utc)
        mock_item = MagicMock()
        mock_item.user_id = "user1"
        mock_item.group_id = "group1"
        mock_item.deliver_by = now + timedelta(hours=1)
        mock_item.settled_threshold = 30
        mock_item.last_related_activity_at = now - timedelta(minutes=5)  # not settled

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_item]
        mock_db.execute = AsyncMock(return_value=mock_result)

        ready = await checker.get_ready_p1_groups("user1")
        assert len(ready) == 0


class TestGetUsersWithQueuedP1:
    @pytest.mark.asyncio
    async def test_returns_distinct_users(self, checker, mock_db):
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = ["user1", "user2"]
        mock_db.execute = AsyncMock(return_value=mock_result)

        users = await checker.get_users_with_queued_p1()
        assert len(users) == 2


class TestIsEodTime:
    @pytest.mark.asyncio
    async def test_matches_eod_time(self, checker):
        """Should return True when current time matches eod_review_time."""
        result = checker.is_eod_time("17:30", "17:30")
        assert result is True

    @pytest.mark.asyncio
    async def test_does_not_match(self, checker):
        result = checker.is_eod_time("17:30", "14:00")
        assert result is False
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd backend && JWT_SECRET=test-secret DATABASE_URL=postgresql+asyncpg://alfred:alfred@localhost:5432/alfred uv run pytest tests/services/test_delivery_checker.py -v
```

- [ ] **Step 3: Implement delivery checker**

Create `backend/app/services/delivery_checker.py`:

```python
"""Delivery checker: determines when message groups are ready for digest delivery.

Stage 3.5 of the agent-driven triage pipeline. No LLM calls.
Runs every 2-3 minutes as a lightweight periodic worker.
"""

import logging
from datetime import datetime, timezone

from sqlalchemy import select, distinct
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.triage import TriageClassification

logger = logging.getLogger(__name__)


class DeliveryChecker:
    """Checks if message groups are ready for delivery based on settle/TTL logic.

    A group is ready when either:
    1. Settled: No new related messages for settled_threshold minutes
    2. Expired: Current time is past deliver_by deadline

    Whichever comes first triggers delivery.
    """

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_users_with_queued_p1(self) -> list[str]:
        """Get user IDs with queued P1 messages (action=summarize_next, queued=True)."""
        result = await self.db.execute(
            select(distinct(TriageClassification.user_id))
            .where(TriageClassification.action == "summarize_next")
            .where(TriageClassification.queued_for_digest == True)  # noqa: E712
            .where(TriageClassification.deliver_by.isnot(None))
        )
        return list(result.scalars().all())

    async def get_ready_p1_groups(self, user_id: str) -> list[dict]:
        """Get P1 message groups that are ready for delivery.

        Returns list of dicts with group_id and message_ids for each ready group.
        """
        now = datetime.now(timezone.utc)

        # Get all queued P1 items for this user
        result = await self.db.execute(
            select(TriageClassification)
            .where(TriageClassification.user_id == user_id)
            .where(TriageClassification.action == "summarize_next")
            .where(TriageClassification.queued_for_digest == True)  # noqa: E712
            .where(TriageClassification.deliver_by.isnot(None))
            .order_by(TriageClassification.created_at.asc())
        )
        items = list(result.scalars().all())

        if not items:
            return []

        # Group items by group_id (NULL group_id = standalone group of 1)
        groups: dict[str | None, list] = {}
        for item in items:
            key = item.group_id or str(item.id)  # Ungrouped items are their own group
            if key not in groups:
                groups[key] = []
            groups[key].append(item)

        ready_groups = []
        for group_key, group_items in groups.items():
            # Check settle: latest last_related_activity_at across all group members
            last_activity = max(
                (i.last_related_activity_at for i in group_items if i.last_related_activity_at),
                default=None,
            )
            settled_threshold = min(
                (i.settled_threshold for i in group_items if i.settled_threshold),
                default=30,
            )
            earliest_deadline = min(
                (i.deliver_by for i in group_items if i.deliver_by),
                default=now,
            )

            # Check if settled
            settled = False
            if last_activity:
                minutes_since_activity = (now - last_activity).total_seconds() / 60
                settled = minutes_since_activity >= settled_threshold

            # Check if TTL expired
            expired = now >= earliest_deadline

            if settled or expired:
                ready_groups.append({
                    "group_id": group_key,
                    "message_ids": [str(i.id) for i in group_items],
                    "reason": "settled" if settled else "expired",
                })

        return ready_groups

    async def get_queued_p2_messages(self, user_id: str) -> list[TriageClassification]:
        """Get all P2 messages queued for EOD digest."""
        result = await self.db.execute(
            select(TriageClassification)
            .where(TriageClassification.user_id == user_id)
            .where(TriageClassification.action == "summarize_eod")
            .where(TriageClassification.queued_for_digest == True)  # noqa: E712
            .where(TriageClassification.is_consolidated == False)  # noqa: E712
            .order_by(TriageClassification.created_at.asc())
        )
        return list(result.scalars().all())

    async def count_p3_messages(self, user_id: str) -> int:
        """Count P3 (ignored) messages for today (for EOD footer)."""
        from sqlalchemy import func

        result = await self.db.execute(
            select(func.count())
            .select_from(TriageClassification)
            .where(TriageClassification.user_id == user_id)
            .where(TriageClassification.action == "ignore")
            .where(TriageClassification.queued_for_digest == False)  # noqa: E712
            .where(TriageClassification.reviewed_at.is_(None))
        )
        return result.scalar() or 0

    def is_eod_time(self, eod_review_time: str, current_time_str: str) -> bool:
        """Check if current time matches user's EOD review time.

        Args:
            eod_review_time: User's configured EOD time as "HH:MM"
            current_time_str: Current local time as "HH:MM"
        """
        return eod_review_time == current_time_str
```

- [ ] **Step 4: Run tests**

```bash
cd backend && JWT_SECRET=test-secret DATABASE_URL=postgresql+asyncpg://alfred:alfred@localhost:5432/alfred uv run pytest tests/services/test_delivery_checker.py -v
```

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/delivery_checker.py backend/tests/services/test_delivery_checker.py
git commit -m "feat(delivery): add delivery checker service

Checks P1 message groups for settle/TTL readiness.
A group is ready when either:
- Settled: no activity for settled_threshold minutes
- Expired: past deliver_by deadline"
```

---

## Task 2: Digest Subagent State and Prompt

**Files:**
- Create: `backend/app/agents/digest/__init__.py`
- Create: `backend/app/agents/digest/state.py`
- Create: `backend/app/agents/digest/prompt.py`

- [ ] **Step 1: Create package**

Create `backend/app/agents/digest/__init__.py`:
```python
"""Digest subagent — groups, summarizes, and delivers message digests."""
```

- [ ] **Step 2: Create state**

Create `backend/app/agents/digest/state.py`:
```python
"""State schema for the digest subagent."""

from typing import Any, TypedDict

from app.core.llm import LLMMessage


class DigestGroup(TypedDict):
    """A group of related messages to include in the digest."""
    group_id: str
    messages: list[dict[str, Any]]  # [{id, sender_name, channel_name, abstract, action, message_ts, thread_ts, slack_permalink}]


class DigestAgentState(TypedDict):
    """State for the digest subagent graph."""

    # Input
    user_id: str
    digest_type: str  # "p1" or "eod"
    groups: list[DigestGroup]
    p3_count: int  # Number of ignored messages (for EOD footer)

    # Agent working state
    llm_messages: list[LLMMessage]
    tool_calls: list | None
    tool_iteration: int
    tool_call_count: int

    # Output
    digest_sent: bool
    digest_record_id: str | None
    error: str | None
```

- [ ] **Step 3: Create prompt**

Create `backend/app/agents/digest/prompt.py`:
```python
"""System prompt for the digest subagent."""

MAX_TOOL_CALLS = 15  # Digest agent may need more calls for fetching context


def build_digest_prompt(digest_type: str, p3_count: int) -> str:
    """Build the system prompt for the digest subagent.

    Args:
        digest_type: "p1" or "eod"
        p3_count: Number of P3 (ignored) messages for EOD footer
    """
    p3_footer = ""
    if digest_type == "eod" and p3_count > 0:
        p3_footer = f"""

## P3 Footer

At the end of the digest, add this line:
---
{p3_count} message{'s' if p3_count != 1 else ''} were auto-ignored today. Review them in the Triage page.
"""

    return f"""\
You are a digest composition agent. Your job is to review a batch of classified
Slack messages, group related ones into conversations, summarize each conversation,
and deliver a formatted digest to the user via Slack DM.

## Your Workflow

1. Review the messages provided in your input. Each message has an abstract
   (summary from the triage agent), sender name, channel, and Slack permalink.

2. Identify which messages are part of the same conversation:
   - Same thread (same thread_ts) → always group together
   - Same channel, related topic → group if they're about the same subject
   - **Messages from the same channel are NOT automatically related** — analyze content

3. For each conversation group, optionally call `fetch_thread` or
   `fetch_channel_history` to get additional context for a better summary.

4. Write a concise summary for each conversation group (1-3 sentences).
   Include key participants and any action items.

5. Call `send_digest_dm` with the formatted digest.

6. Call `save_digest_record` to persist the digest for the UI.

7. Call `mark_delivered` to update message statuses.

## Formatting Rules

{"Format as a P1 digest (important, needs attention soon):" if digest_type == "p1" else "Format as an End of Day digest:"}

- Each conversation group gets its own section
- Include the channel name and participants
- Include Slack permalinks for each conversation
- Order by importance (P1 before P2)
- Keep summaries concise — the user wants a quick scan, not a wall of text

## CRITICAL: Do Not Over-Summarize

You will receive multiple messages. NOT all messages are related to each other.
- Identify which messages are part of the same conversation
- Messages from the same channel are NOT automatically related — analyze the content
- Summarize each conversation group independently
- Do NOT combine unrelated messages into a single summary
- Each conversation group gets its own section in the digest

## Tool Call Limit

You have a maximum of {MAX_TOOL_CALLS} tool calls. Use them wisely.
Prioritize fetching context for messages where the abstract alone isn't enough.
{p3_footer}"""
```

- [ ] **Step 4: Commit**

```bash
git add backend/app/agents/digest/
git commit -m "feat(digest-agent): add state schema and system prompt

DigestAgentState tracks groups, LLM messages, and delivery output.
Prompt instructs agent to group related messages, summarize selectively,
and format digest for Slack DM delivery."
```

---

## Task 3: Digest Subagent Tools

**Files:**
- Create: `backend/app/agents/digest/tools/__init__.py`
- Create: `backend/app/agents/digest/tools/fetch_thread.py`
- Create: `backend/app/agents/digest/tools/fetch_channel_history.py`
- Create: `backend/app/agents/digest/tools/send_digest_dm.py`
- Create: `backend/app/agents/digest/tools/save_digest_record.py`
- Create: `backend/app/agents/digest/tools/mark_delivered.py`
- Create: `backend/tests/agents/digest/__init__.py`
- Create: `backend/tests/agents/digest/test_digest_tools.py`

- [ ] **Step 1: Create tools package init**

Create `backend/app/agents/digest/tools/__init__.py`:
```python
"""Digest subagent tools."""

from app.tools.registry import ToolRegistry

from .fetch_thread import DigestFetchThreadTool
from .fetch_channel_history import DigestFetchChannelHistoryTool
from .send_digest_dm import SendDigestDmTool
from .save_digest_record import SaveDigestRecordTool
from .mark_delivered import MarkDeliveredTool


def get_digest_tool_registry() -> ToolRegistry:
    """Create a tool registry with all digest subagent tools."""
    registry = ToolRegistry()
    registry.register(DigestFetchThreadTool())
    registry.register(DigestFetchChannelHistoryTool())
    registry.register(SendDigestDmTool())
    registry.register(SaveDigestRecordTool())
    registry.register(MarkDeliveredTool())
    return registry
```

- [ ] **Step 2: Create fetch_thread and fetch_channel_history tools**

These are similar to the triage agent's tools but named differently to avoid conflicts in the registry. Create `backend/app/agents/digest/tools/fetch_thread.py` and `fetch_channel_history.py` following the same pattern as the triage agent's tools in `backend/app/agents/triage/tools/`. They use `get_slack_service().client` to call `conversations.replies` and `conversations.history` respectively.

- [ ] **Step 3: Create SendDigestDmTool**

Create `backend/app/agents/digest/tools/send_digest_dm.py`:

```python
"""Tool to send a formatted digest to the user via Slack DM."""

import json
import logging
from typing import Any

from app.tools.base import BaseTool, ToolContext

logger = logging.getLogger(__name__)


class SendDigestDmTool(BaseTool):
    name = "send_digest_dm"
    description = (
        "Send the formatted digest to the user via Slack DM. "
        "Provide the complete digest text formatted with Slack mrkdwn."
    )
    parameters_schema = {
        "type": "object",
        "properties": {
            "digest_text": {
                "type": "string",
                "description": "The complete digest message in Slack mrkdwn format",
            },
        },
        "required": ["digest_text"],
    }
    max_iterations = 1

    async def execute(self, *, context: ToolContext | None = None, **kwargs: Any) -> str:
        if not context or "db" not in context or "user_id" not in context:
            return json.dumps({"error": "Missing db or user_id in context"})

        user_id = context["user_id"]
        digest_text = kwargs["digest_text"]
        db = context["db"]

        from app.db.repositories import UserRepository
        from app.services.slack import get_slack_service

        user_repo = UserRepository(db)
        user = await user_repo.get(user_id)

        if not user or not user.slack_user_id:
            return json.dumps({"error": "User not found or no Slack ID"})

        slack = get_slack_service()
        try:
            await slack.send_message(channel=user.slack_user_id, text=digest_text)
            return json.dumps({"status": "sent", "user_slack_id": user.slack_user_id})
        except Exception as e:
            logger.exception("Failed to send digest DM")
            return json.dumps({"error": f"Failed to send DM: {str(e)}"})
```

- [ ] **Step 4: Create SaveDigestRecordTool**

Create `backend/app/agents/digest/tools/save_digest_record.py`:

```python
"""Tool to persist a digest record to the database."""

import json
import logging
from typing import Any

from app.tools.base import BaseTool, ToolContext

logger = logging.getLogger(__name__)


class SaveDigestRecordTool(BaseTool):
    name = "save_digest_record"
    description = (
        "Save the digest record to the database for display in the UI. "
        "Provide the digest summary text and the list of message IDs included."
    )
    parameters_schema = {
        "type": "object",
        "properties": {
            "summary_text": {
                "type": "string",
                "description": "Brief summary of the entire digest",
            },
            "message_ids": {
                "type": "array",
                "items": {"type": "string"},
                "description": "IDs of all TriageClassification records included in this digest",
            },
            "digest_type": {
                "type": "string",
                "enum": ["p1", "eod"],
                "description": "Type of digest",
            },
        },
        "required": ["summary_text", "message_ids", "digest_type"],
    }
    max_iterations = 1

    async def execute(self, *, context: ToolContext | None = None, **kwargs: Any) -> str:
        if not context or "db" not in context or "user_id" not in context:
            return json.dumps({"error": "Missing db or user_id in context"})

        user_id = context["user_id"]
        db = context["db"]
        summary_text = kwargs["summary_text"]
        message_ids = kwargs["message_ids"]
        digest_type = kwargs.get("digest_type", "p1")

        from app.db.models.triage import TriageClassification
        from app.db.repositories.triage import TriageClassificationRepository

        repo = TriageClassificationRepository(db)

        # Create a consolidated summary record
        summary = TriageClassification(
            user_id=user_id,
            sender_slack_id="",
            channel_id="",
            message_ts="",
            action="summarize_eod" if digest_type == "eod" else "summarize_next",
            is_consolidated=True,
            abstract=summary_text,
            classification_path="digest",
            child_count=len(message_ids),
            digest_type="scheduled",
            queued_for_digest=False,
            confidence=1.0,
            classification_reason="Agent-generated digest summary",
        )
        summary = await repo.create(summary)
        await db.flush()

        # Link child messages to this summary
        if message_ids:
            from sqlalchemy import update

            await db.execute(
                update(TriageClassification)
                .where(TriageClassification.id.in_(message_ids))
                .values(digest_summary_id=summary.id)
            )
            await db.flush()

        return json.dumps({
            "status": "saved",
            "digest_record_id": str(summary.id),
            "message_count": len(message_ids),
        })
```

- [ ] **Step 5: Create MarkDeliveredTool**

Create `backend/app/agents/digest/tools/mark_delivered.py`:

```python
"""Tool to mark messages as delivered after digest is sent."""

import json
import logging
from typing import Any

from app.tools.base import BaseTool, ToolContext

logger = logging.getLogger(__name__)


class MarkDeliveredTool(BaseTool):
    name = "mark_delivered"
    description = (
        "Mark messages as delivered after the digest has been sent. "
        "This clears queued_for_digest and sets the processed_reason."
    )
    parameters_schema = {
        "type": "object",
        "properties": {
            "message_ids": {
                "type": "array",
                "items": {"type": "string"},
                "description": "IDs of TriageClassification records to mark as delivered",
            },
        },
        "required": ["message_ids"],
    }
    max_iterations = 1

    async def execute(self, *, context: ToolContext | None = None, **kwargs: Any) -> str:
        if not context or "db" not in context:
            return json.dumps({"error": "Missing db in context"})

        message_ids = kwargs["message_ids"]
        db = context["db"]

        if not message_ids:
            return json.dumps({"status": "no_messages", "count": 0})

        from sqlalchemy import update
        from app.db.models.triage import TriageClassification

        result = await db.execute(
            update(TriageClassification)
            .where(TriageClassification.id.in_(message_ids))
            .values(
                queued_for_digest=False,
                processed_reason="summarized",
            )
        )
        await db.flush()

        return json.dumps({
            "status": "marked",
            "count": result.rowcount,
        })
```

- [ ] **Step 6: Write tool tests**

Create `backend/tests/agents/digest/__init__.py` (empty) and `backend/tests/agents/digest/test_digest_tools.py` with tests for SendDigestDmTool, SaveDigestRecordTool, and MarkDeliveredTool. Follow the same pattern as `backend/tests/agents/triage/test_triage_tools.py`.

- [ ] **Step 7: Run tests**

```bash
cd backend && JWT_SECRET=test-secret DATABASE_URL=postgresql+asyncpg://alfred:alfred@localhost:5432/alfred uv run pytest tests/agents/digest/ -v
```

- [ ] **Step 8: Commit**

```bash
git add backend/app/agents/digest/tools/ backend/tests/agents/digest/
git commit -m "feat(digest-agent): add digest subagent tools

Tools: fetch_thread, fetch_channel_history, send_digest_dm,
save_digest_record, mark_delivered."
```

---

## Task 4: Digest Subagent Graph and Agent Class

**Files:**
- Create: `backend/app/agents/digest/nodes.py`
- Create: `backend/app/agents/digest/graph.py`
- Create: `backend/app/agents/digest/agent.py`

- [ ] **Step 1: Create node functions**

Create `backend/app/agents/digest/nodes.py` with:

- `setup_node(state, config)`: Build system prompt, create user message listing all message groups with abstracts, set initial state
- `llm_node(state, config)`: Call LLM with tool definitions, same pattern as triage agent's llm_node
- `tool_node(state, config)`: Execute tool calls, track tool_call_count, enforce MAX_TOOL_CALLS limit, check for digest_sent status
- `route_after_llm(state)`: Route to tool_node or end
- `route_after_tool(state)`: Route to llm_node or end (end when digest_sent)

The setup node should format all message groups into a structured user message:
```
You have {N} message groups to compose into a digest.

Group 1 (group_id: abc-123):
- Message from Felix in #engineering-leads: "Meeting discussion about standup time" [permalink]
- Message from Matt in #engineering-leads: "Response about standup" [permalink]

Group 2 (ungrouped):
- Message from Anam in #shipping: "Database fix update" [permalink]

Compose a digest and deliver it.
```

- [ ] **Step 2: Create graph**

Create `backend/app/agents/digest/graph.py`:
```python
from langgraph.graph import END, StateGraph
from app.agents.digest.state import DigestAgentState

def create_digest_graph():
    builder = StateGraph(DigestAgentState)
    builder.add_node("setup", setup_node)
    builder.add_node("llm_node", llm_node)
    builder.add_node("tool_node", tool_node)
    builder.set_entry_point("setup")
    builder.add_edge("setup", "llm_node")
    builder.add_conditional_edges("llm_node", route_after_llm, {"tool_node": "tool_node", "end": END})
    builder.add_conditional_edges("tool_node", route_after_tool, {"llm_node": "llm_node", "end": END})
    return builder.compile()
```

- [ ] **Step 3: Create agent class**

Create `backend/app/agents/digest/agent.py`:
```python
class DigestAgent:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.graph = create_digest_graph()
        self.tool_registry = get_digest_tool_registry()

    async def compose_and_deliver(
        self,
        user_id: str,
        digest_type: str,  # "p1" or "eod"
        groups: list[dict],  # [{group_id, messages: [{id, sender_name, channel_name, abstract, ...}]}]
        p3_count: int = 0,
    ) -> dict:
        # Build initial state, invoke graph, return result
        # Returns {digest_sent, digest_record_id, error}
```

- [ ] **Step 4: Commit**

```bash
git add backend/app/agents/digest/nodes.py backend/app/agents/digest/graph.py backend/app/agents/digest/agent.py
git commit -m "feat(digest-agent): add graph, nodes, and agent class

LangGraph StateGraph: setup -> llm_node -> tool_node cycle.
DigestAgent.compose_and_deliver() is the main entry point."
```

---

## Task 5: Worker Tasks and Cron Job

**Files:**
- Modify: `backend/app/worker/tasks.py`
- Modify: `backend/app/worker/main.py`

- [ ] **Step 1: Add check_delivery_readiness task**

Add to `backend/app/worker/tasks.py`:

```python
async def check_delivery_readiness(ctx: dict) -> dict:
    """Check if any message groups are ready for delivery.

    Runs every 2-3 minutes. For users with use_agent_triage=True:
    - Checks P1 groups for settle/TTL readiness
    - Checks EOD time for P2 digest delivery
    - Dispatches digest subagent for ready batches
    """
    from app.services.delivery_checker import DeliveryChecker
    from app.db.repositories.triage import TriageUserSettingsRepository
    from app.worker.scheduler import get_redis_pool

    async with get_db_session() as db:
        checker = DeliveryChecker(db)
        settings_repo = TriageUserSettingsRepository(db)
        pool = await get_redis_pool()

        # Check P1 groups
        users_with_p1 = await checker.get_users_with_queued_p1()
        p1_dispatched = 0

        for user_id in users_with_p1:
            settings = await settings_repo.get_by_user_id(user_id)
            if not settings or not settings.use_agent_triage:
                continue  # Skip users on old pipeline

            ready_groups = await checker.get_ready_p1_groups(user_id)
            if ready_groups:
                # Batch all ready groups into one digest
                await pool.enqueue_job(
                    "run_digest_agent",
                    user_id=user_id,
                    digest_type="p1",
                    group_data=ready_groups,
                    p3_count=0,
                )
                p1_dispatched += 1

        # Check EOD digests
        eod_dispatched = 0
        all_settings = await settings_repo.get_all_always_on()

        for settings in all_settings:
            if not settings.use_agent_triage:
                continue
            if not settings.eod_review_time:
                continue

            from app.services.triage_delivery import get_user_timezone, get_current_time_in_tz

            user_tz = await get_user_timezone(db, str(settings.user_id))
            current_time = get_current_time_in_tz(user_tz)
            current_hhmm = current_time.strftime("%H:%M")

            if checker.is_eod_time(settings.eod_review_time, current_hhmm):
                p2_messages = await checker.get_queued_p2_messages(str(settings.user_id))
                p3_count = await checker.count_p3_messages(str(settings.user_id))

                if p2_messages or p3_count > 0:
                    # Build groups from P2 messages
                    p2_groups = []
                    for msg in p2_messages:
                        p2_groups.append({
                            "group_id": msg.group_id or str(msg.id),
                            "message_ids": [str(msg.id)],
                        })

                    await pool.enqueue_job(
                        "run_digest_agent",
                        user_id=str(settings.user_id),
                        digest_type="eod",
                        group_data=p2_groups,
                        p3_count=p3_count,
                    )
                    eod_dispatched += 1

    return {
        "p1_dispatched": p1_dispatched,
        "eod_dispatched": eod_dispatched,
    }
```

- [ ] **Step 2: Add run_digest_agent task**

```python
async def run_digest_agent(
    ctx: dict,
    user_id: str,
    digest_type: str,
    group_data: list[dict],
    p3_count: int = 0,
) -> dict:
    """Run the digest subagent to compose and deliver a digest."""
    from app.agents.digest.agent import DigestAgent
    from app.db.repositories.triage import TriageClassificationRepository

    async with get_db_session() as db:
        repo = TriageClassificationRepository(db)

        # Hydrate groups with message data from DB
        groups = []
        for group in group_data:
            messages = []
            for msg_id in group["message_ids"]:
                item = await repo.get(msg_id)
                if item:
                    messages.append({
                        "id": str(item.id),
                        "sender_name": item.sender_name or "",
                        "channel_name": item.channel_name or "",
                        "abstract": item.abstract or "",
                        "action": item.action,
                        "message_ts": item.message_ts,
                        "thread_ts": item.thread_ts,
                        "slack_permalink": item.slack_permalink or "",
                    })
            if messages:
                groups.append({
                    "group_id": group["group_id"],
                    "messages": messages,
                })

        if not groups:
            return {"status": "no_messages"}

        agent = DigestAgent(db)
        result = await agent.compose_and_deliver(
            user_id=user_id,
            digest_type=digest_type,
            groups=groups,
            p3_count=p3_count,
        )

        await db.commit()

        logger.info(
            f"Digest agent completed for user {user_id}: "
            f"type={digest_type}, sent={result.get('digest_sent')}"
        )
        return result
```

- [ ] **Step 3: Register tasks and add cron job**

In `backend/app/worker/main.py`:
- Add `check_delivery_readiness` and `run_digest_agent` to imports and functions list
- Add cron job for `check_delivery_readiness` running every 3 minutes:
```python
cron_jobs.append(
    cron(
        check_delivery_readiness,
        minute={0, 3, 6, 9, 12, 15, 18, 21, 24, 27, 30, 33, 36, 39, 42, 45, 48, 51, 54, 57},
    )
)
```

- [ ] **Step 4: Commit**

```bash
git add backend/app/worker/tasks.py backend/app/worker/main.py
git commit -m "feat(delivery): add delivery checker cron and digest agent worker task

check_delivery_readiness runs every 3 min:
- P1: checks settle/TTL, batches ready groups, dispatches digest agent
- EOD: checks eod_review_time, dispatches digest agent with P2 messages
- Only runs for users with use_agent_triage=True

run_digest_agent hydrates message data and invokes DigestAgent."
```

---

## Task 6: Integration Tests

**Files:**
- Create: `backend/tests/agents/digest/test_digest_agent.py`

- [ ] **Step 1: Write agent integration tests**

```python
class TestDigestAgentComposeAndDeliver:
    @pytest.mark.asyncio
    async def test_returns_result_structure(self):
        """Verify agent returns expected result keys."""

    @pytest.mark.asyncio
    async def test_handles_error_gracefully(self):
        """Agent should return error dict, not raise."""


class TestDigestToolRegistry:
    def test_registry_has_all_tools(self):
        """Verify all 5 tools are registered."""

    def test_registry_returns_definitions(self):
        """Verify tool definitions are generated."""


class TestDeliveryCheckerIntegration:
    @pytest.mark.asyncio
    async def test_ungrouped_messages_treated_as_individual_groups(self):
        """Messages without group_id are each their own group."""

    @pytest.mark.asyncio
    async def test_grouped_messages_use_highest_priority_timing(self):
        """Group delivery uses shortest settle threshold."""
```

- [ ] **Step 2: Run tests**

```bash
cd backend && JWT_SECRET=test-secret DATABASE_URL=postgresql+asyncpg://alfred:alfred@localhost:5432/alfred uv run pytest tests/agents/digest/ tests/services/test_delivery_checker.py -v
```

- [ ] **Step 3: Commit**

```bash
git add backend/tests/agents/digest/
git commit -m "test(digest-agent): add integration and tool registry tests"
```

---

## Task 7: Deploy and Verify

- [ ] **Step 1: Run all tests**

```bash
cd backend && JWT_SECRET=test-secret DATABASE_URL=postgresql+asyncpg://alfred:alfred@localhost:5432/alfred uv run pytest tests/agents/ tests/services/test_delivery_checker.py tests/services/test_triage_cache.py tests/services/test_triage_prefilter.py -v
```

- [ ] **Step 2: Push and deploy**

```bash
git push origin slack-triage-refactor-3
gcloud compute ssh --zone "us-central1-c" "alfred-pa" --project "tyler-knotek-e1ltzltz-af40" --command "cd /opt/alfred && sudo git pull && sudo docker compose -f docker-compose.prod.yml up -d --build backend worker"
```

- [ ] **Step 3: Verify in production**

With `use_agent_triage=true` for your user:
1. Send test messages in monitored channels
2. Wait for P1 settle threshold (30 min) or TTL (1 hr)
3. Check worker logs for digest agent execution
4. Verify Slack DM digest is received
5. Check triage UI shows the digest record

---

## Transition Notes

- The delivery checker only runs for users with `use_agent_triage=True`
- Users on the old pipeline continue to use `check_delivery_triggers` and `deliver_eod_digests` cron jobs
- Both old and new delivery systems can run simultaneously (they check different user sets)
- Plan 4 (Cleanup) will remove the old delivery system after full rollout
