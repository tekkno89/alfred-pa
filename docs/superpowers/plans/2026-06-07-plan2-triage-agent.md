# Plan 2: Triage Agent with Tools

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a LangGraph ReAct agent that classifies Slack messages using tools for context gathering, and replaces the deterministic TriagePipeline with a feature-flagged switchover.

**Architecture:** A LangGraph `StateGraph` with a ReAct loop. The agent receives a message reference + user config, calls tools to fetch message text, check queued messages, gather context, then takes a terminal action (alert_now, queue_for_digest, or link_messages + queue_for_digest). Tools follow the existing `BaseTool` pattern. A feature flag on `TriageUserSettings` controls which pipeline processes each user's messages.

**Tech Stack:** Python 3.11+, LangGraph, Vertex AI (Gemini), SQLAlchemy 2.0, Redis, Slack API, ARQ

**Spec:** `docs/superpowers/specs/2026-05-31-agent-driven-triage-design.md`

---

## File Structure

### New Files
- `backend/app/agents/triage/__init__.py`
- `backend/app/agents/triage/state.py` — TriageAgentState TypedDict
- `backend/app/agents/triage/prompt.py` — System prompt template
- `backend/app/agents/triage/graph.py` — StateGraph construction
- `backend/app/agents/triage/nodes.py` — Node functions (setup, llm, tool, finalize)
- `backend/app/agents/triage/tools/__init__.py` — Tool registry for triage agent
- `backend/app/agents/triage/tools/fetch_message.py` — Fetch message text from Slack
- `backend/app/agents/triage/tools/fetch_thread.py` — Fetch thread replies
- `backend/app/agents/triage/tools/fetch_channel_history.py` — Fetch recent channel messages
- `backend/app/agents/triage/tools/get_queued_messages.py` — Get queued classifications
- `backend/app/agents/triage/tools/get_user_channel_rules.py` — Get cached channel rules
- `backend/app/agents/triage/tools/alert_now.py` — Immediate P0 notification
- `backend/app/agents/triage/tools/queue_for_digest.py` — Queue for later digest
- `backend/app/agents/triage/tools/link_messages.py` — Link related messages
- `backend/tests/agents/triage/test_triage_agent.py` — Agent integration tests
- `backend/tests/agents/triage/test_triage_tools.py` — Tool unit tests

### Modified Files
- `backend/app/db/models/triage.py` — Add `use_agent_triage` feature flag to TriageUserSettings
- `backend/app/worker/tasks.py` — Add `run_triage_agent` task, modify `prefilter_triage_message` to check feature flag
- `backend/app/worker/main.py` — Register new task
- `backend/alembic/versions/057_add_agent_triage_flag.py` — Migration for feature flag

---

## Task 1: Agent State and Prompt

**Files:**
- Create: `backend/app/agents/triage/__init__.py`
- Create: `backend/app/agents/triage/state.py`
- Create: `backend/app/agents/triage/prompt.py`

- [ ] **Step 1: Create package init**

Create `backend/app/agents/triage/__init__.py`:
```python
"""Triage agent — classifies Slack messages using tools for context gathering."""
```

- [ ] **Step 2: Create agent state**

Create `backend/app/agents/triage/state.py`:
```python
"""State schema for the triage agent."""

from typing import Any, TypedDict

from app.core.llm import LLMMessage


class TriageAgentState(TypedDict):
    """State for the triage agent graph."""

    # Input (set once at start)
    user_id: str
    channel_id: str
    message_ts: str
    thread_ts: str | None
    sender_slack_id: str
    event_type: str  # "message" or "app_mention"
    bot_id: str | None
    message_text_fallback: str  # Transition: text from old pipeline, empty when agent fetches

    # User config (set once at start)
    sensitivity: str
    custom_rules: str | None
    p0_definition: str | None
    p1_definition: str | None
    p2_definition: str | None
    p3_definition: str | None
    p1_max_wait_minutes: int
    p1_settled_threshold_minutes: int
    eod_review_time: str

    # Agent working state
    llm_messages: list[LLMMessage]
    tool_calls: list | None
    tool_iteration: int
    tool_call_count: int  # Total tool calls across all iterations

    # Output
    action_taken: str | None  # "alert_now", "queue_for_digest", or None
    classification_id: str | None  # ID of created TriageClassification
    error: str | None

    # Metadata
    needs_review: bool
```

- [ ] **Step 3: Create system prompt**

Create `backend/app/agents/triage/prompt.py`:
```python
"""System prompt for the triage agent."""

# Default definitions — P3 intentionally has no default (user-defined only)
DEFAULT_P0 = (
    "Requires IMMEDIATE attention and action RIGHT NOW.\n\n"
    "Use ONLY when the message explicitly indicates an urgent situation that needs "
    "your response within minutes, not hours or days.\n\n"
    "Examples: Active emergencies, explicit requests marked 'urgent'/'critical'/'ASAP', "
    "time-sensitive decisions that will be made without you if you don't respond now.\n\n"
    "DO NOT use for:\n"
    "- Status updates (even about serious topics)\n"
    "- Messages about resolved or past issues\n"
    "- FYI messages about incidents that are being handled\n"
    "- Information that's important but doesn't require immediate action"
)

DEFAULT_P1 = (
    "Needs your attention within hours (today or tomorrow).\n\n"
    "Use for requests that need a response, questions that need your input, "
    "or time-sensitive items that aren't emergencies.\n\n"
    "Examples: Meeting requests, questions requiring your expertise, "
    "decisions that can wait a few hours but not days."
)

DEFAULT_P2 = (
    "Notable information to review at end of day.\n\n"
    "Use for updates, FYIs, discussions, and information worth knowing "
    "but not requiring immediate action.\n\n"
    "Examples: Project updates, team announcements, interesting discussions, "
    "status reports, resolved issues, informational content."
)

MAX_TOOL_CALLS = 10


def build_system_prompt(
    sensitivity: str,
    custom_rules: str | None,
    p0_definition: str | None,
    p1_definition: str | None,
    p2_definition: str | None,
    p3_definition: str | None,
) -> str:
    """Build the system prompt for the triage agent."""

    p0_def = p0_definition or DEFAULT_P0
    p1_def = p1_definition or DEFAULT_P1
    p2_def = p2_definition or DEFAULT_P2
    p3_section = ""
    if p3_definition:
        p3_section = f"- **P3 (ignore):** {p3_definition}"
    else:
        p3_section = "- **P3 (ignore):** Not configured. If unsure, classify as P2 instead."

    sensitivity_guidance = {
        "low": "Be conservative. Only classify as P0 for genuine emergencies.",
        "medium": "Use balanced judgment. P0 for urgent matters, P1 for time-sensitive requests.",
        "high": "Be liberal with P0/P1. Anything that could be important should be surfaced.",
    }

    prompt = f"""You are a message triage agent. Your job is to classify a Slack message and decide what to do with it.

## Your Workflow

1. **ALWAYS start** by calling `fetch_message` to get the message text.
2. **ALWAYS call** `get_queued_messages` next to see what's already classified for this user in this channel.
3. Analyze the message meaning and decide if you need more context:
   - Is this a thread reply? Call `fetch_thread` to see the full thread.
   - Is this part of a channel conversation? Call `fetch_channel_history` to see recent messages.
   - Does this channel have special rules? Call `get_user_channel_rules`.
4. Check if this message is related to any queued messages — if so, call `link_messages`.
5. Classify and take ONE terminal action: `alert_now`, `queue_for_digest`.

## Priority Definitions

- **P0 (notify_now):** {p0_def}
- **P1 (summarize_next):** {p1_def}
- **P2 (summarize_eod):** {p2_def}
{p3_section}

## Sensitivity: {sensitivity}
{sensitivity_guidance.get(sensitivity, sensitivity_guidance["medium"])}

## CRITICAL: Semantic Analysis

Analyze the FULL message context and meaning, not just keywords.

Before classifying, ask yourself:
1. What is the ACTUAL intent of this message?
2. Is this describing an ACTIVE situation or a RESOLVED one?
3. Does this require action from the user, or is it informational?
4. What would a reasonable person want to do with this information?

Keyword traps to avoid:
- Words like "crash", "error", "issue" don't automatically mean urgent
- Look for indicators like "resolved", "fixed", "back up", "working now"
- A message about a "database crash" that says "it's resolved now" is informational, not urgent
- Consider the tense: "is crashing" (active) vs "crashed" (past) vs "was crashing but is fixed" (resolved)

Classify based on what action the user needs to take, not what topics are mentioned.

## Terminal Actions

You MUST take exactly one of these actions:

- `alert_now`: Send an immediate P0 notification. Use ONLY for truly urgent messages.
- `queue_for_digest`: Queue the message for a digest. Provide the priority (P0/P1/P2/P3) and a brief abstract.

If you called `link_messages` to link to an existing queued message, you still must call `queue_for_digest` afterward.

## Tool Call Limit

You have a maximum of {MAX_TOOL_CALLS} tool calls per message. Use them wisely.
Always call `fetch_message` and `get_queued_messages` first (2 calls minimum).
"""

    if custom_rules:
        prompt += f"""
## User-Defined Classification Rules

Follow these rules provided by the user:
{custom_rules}
"""

    return prompt
```

- [ ] **Step 4: Commit**

```bash
git add backend/app/agents/triage/
git commit -m "feat(triage-agent): add state schema and system prompt

TriageAgentState tracks message ref, user config, LLM messages,
tool calls, and classification output. System prompt includes
semantic analysis guidance and configurable priority definitions."
```

---

## Task 2: Context-Gathering Tools

**Files:**
- Create: `backend/app/agents/triage/tools/__init__.py`
- Create: `backend/app/agents/triage/tools/fetch_message.py`
- Create: `backend/app/agents/triage/tools/fetch_thread.py`
- Create: `backend/app/agents/triage/tools/fetch_channel_history.py`
- Create: `backend/app/agents/triage/tools/get_queued_messages.py`
- Create: `backend/app/agents/triage/tools/get_user_channel_rules.py`
- Create: `backend/tests/agents/triage/test_triage_tools.py`

- [ ] **Step 1: Create tools package init**

Create `backend/app/agents/triage/tools/__init__.py`:
```python
"""Triage agent tools."""

from app.tools.base import ToolRegistry

from .fetch_message import FetchMessageTool
from .fetch_thread import FetchThreadTool
from .fetch_channel_history import FetchChannelHistoryTool
from .get_queued_messages import GetQueuedMessagesTool
from .get_user_channel_rules import GetUserChannelRulesTool
from .alert_now import AlertNowTool
from .queue_for_digest import QueueForDigestTool
from .link_messages import LinkMessagesTool


def get_triage_tool_registry() -> ToolRegistry:
    """Create a tool registry with all triage agent tools."""
    registry = ToolRegistry()
    registry.register(FetchMessageTool())
    registry.register(FetchThreadTool())
    registry.register(FetchChannelHistoryTool())
    registry.register(GetQueuedMessagesTool())
    registry.register(GetUserChannelRulesTool())
    registry.register(AlertNowTool())
    registry.register(QueueForDigestTool())
    registry.register(LinkMessagesTool())
    return registry
```

- [ ] **Step 2: Create FetchMessageTool**

Create `backend/app/agents/triage/tools/fetch_message.py`:
```python
"""Tool to fetch a single message's text from Slack API."""

import json
from typing import Any

from app.tools.base import BaseTool, ToolContext


class FetchMessageTool(BaseTool):
    name = "fetch_message"
    description = (
        "Fetch a message's text from Slack. Call this FIRST before classifying. "
        "Returns the message text, sender info, and permalink."
    )
    parameters_schema = {
        "type": "object",
        "properties": {
            "channel_id": {"type": "string", "description": "Slack channel ID"},
            "message_ts": {"type": "string", "description": "Message timestamp"},
        },
        "required": ["channel_id", "message_ts"],
    }
    max_iterations = 1

    async def execute(self, *, context: ToolContext | None = None, **kwargs: Any) -> str:
        channel_id = kwargs["channel_id"]
        message_ts = kwargs["message_ts"]

        from app.services.slack import get_slack_service

        slack = get_slack_service()
        try:
            result = await slack.client.conversations_history(
                channel=channel_id,
                oldest=message_ts,
                inclusive=True,
                limit=1,
            )
            messages = result.get("messages", [])
            if not messages:
                return json.dumps({"error": "Message not found"})

            msg = messages[0]
            return json.dumps({
                "text": msg.get("text", ""),
                "user": msg.get("user", ""),
                "ts": msg.get("ts", ""),
                "thread_ts": msg.get("thread_ts"),
            })
        except Exception as e:
            return json.dumps({"error": f"Failed to fetch message: {str(e)}"})
```

- [ ] **Step 3: Create FetchThreadTool**

Create `backend/app/agents/triage/tools/fetch_thread.py`:
```python
"""Tool to fetch thread replies from Slack API."""

import json
from typing import Any

from app.tools.base import BaseTool, ToolContext


class FetchThreadTool(BaseTool):
    name = "fetch_thread"
    description = (
        "Fetch thread messages for context. Use when the message is a thread reply "
        "(has thread_ts) or when you want to see replies to a message."
    )
    parameters_schema = {
        "type": "object",
        "properties": {
            "channel_id": {"type": "string", "description": "Slack channel ID"},
            "thread_ts": {"type": "string", "description": "Thread parent timestamp"},
            "limit": {
                "type": "integer",
                "description": "Max messages to return (default 10)",
                "default": 10,
            },
        },
        "required": ["channel_id", "thread_ts"],
    }
    max_iterations = 2

    async def execute(self, *, context: ToolContext | None = None, **kwargs: Any) -> str:
        channel_id = kwargs["channel_id"]
        thread_ts = kwargs["thread_ts"]
        limit = kwargs.get("limit", 10)

        from app.services.slack import get_slack_service

        slack = get_slack_service()
        try:
            result = await slack.client.conversations_replies(
                channel=channel_id,
                ts=thread_ts,
                limit=limit,
            )
            messages = result.get("messages", [])
            formatted = []
            for msg in messages:
                formatted.append({
                    "user": msg.get("user", "unknown"),
                    "text": msg.get("text", ""),
                    "ts": msg.get("ts", ""),
                })
            return json.dumps({"messages": formatted, "count": len(formatted)})
        except Exception as e:
            return json.dumps({"error": f"Failed to fetch thread: {str(e)}"})
```

- [ ] **Step 4: Create FetchChannelHistoryTool**

Create `backend/app/agents/triage/tools/fetch_channel_history.py`:
```python
"""Tool to fetch recent channel messages from Slack API."""

import json
from typing import Any

from app.tools.base import BaseTool, ToolContext


class FetchChannelHistoryTool(BaseTool):
    name = "fetch_channel_history"
    description = (
        "Fetch recent messages from a channel. Use to understand if a message "
        "is part of an ongoing conversation that didn't happen in a thread."
    )
    parameters_schema = {
        "type": "object",
        "properties": {
            "channel_id": {"type": "string", "description": "Slack channel ID"},
            "limit": {
                "type": "integer",
                "description": "Max messages to return (default 10)",
                "default": 10,
            },
        },
        "required": ["channel_id"],
    }
    max_iterations = 2

    async def execute(self, *, context: ToolContext | None = None, **kwargs: Any) -> str:
        channel_id = kwargs["channel_id"]
        limit = kwargs.get("limit", 10)

        from app.services.slack import get_slack_service

        slack = get_slack_service()
        try:
            result = await slack.client.conversations_history(
                channel=channel_id,
                limit=limit,
            )
            messages = result.get("messages", [])
            formatted = []
            for msg in messages:
                # Skip thread replies to show only top-level messages
                if msg.get("thread_ts") and msg.get("thread_ts") != msg.get("ts"):
                    continue
                formatted.append({
                    "user": msg.get("user", "unknown"),
                    "text": msg.get("text", ""),
                    "ts": msg.get("ts", ""),
                    "thread_ts": msg.get("thread_ts"),
                })
            return json.dumps({"messages": formatted, "count": len(formatted)})
        except Exception as e:
            return json.dumps({"error": f"Failed to fetch channel history: {str(e)}"})
```

- [ ] **Step 5: Create GetQueuedMessagesTool**

Create `backend/app/agents/triage/tools/get_queued_messages.py`:
```python
"""Tool to get messages already queued for this user."""

import json
from typing import Any

from app.tools.base import BaseTool, ToolContext


class GetQueuedMessagesTool(BaseTool):
    name = "get_queued_messages"
    description = (
        "Get messages already queued for digest for this user in this channel. "
        "Call this SECOND (after fetch_message) to see if there are related messages "
        "you should link to."
    )
    parameters_schema = {
        "type": "object",
        "properties": {
            "channel_id": {"type": "string", "description": "Slack channel ID"},
        },
        "required": ["channel_id"],
    }
    max_iterations = 1

    async def execute(self, *, context: ToolContext | None = None, **kwargs: Any) -> str:
        if not context or "db" not in context or "user_id" not in context:
            return json.dumps({"error": "Missing db or user_id in context"})

        channel_id = kwargs["channel_id"]
        user_id = context["user_id"]

        from sqlalchemy import select
        from app.db.models.triage import TriageClassification

        db = context["db"]
        result = await db.execute(
            select(TriageClassification)
            .where(TriageClassification.user_id == user_id)
            .where(TriageClassification.channel_id == channel_id)
            .where(TriageClassification.queued_for_digest == True)  # noqa: E712
            .order_by(TriageClassification.created_at.desc())
            .limit(10)
        )
        items = list(result.scalars().all())

        if not items:
            return json.dumps({"messages": [], "count": 0})

        formatted = []
        for item in items:
            formatted.append({
                "id": str(item.id),
                "sender_name": item.sender_name,
                "abstract": item.abstract,
                "action": item.action,
                "group_id": item.group_id,
                "message_ts": item.message_ts,
                "channel_name": item.channel_name,
            })

        return json.dumps({"messages": formatted, "count": len(formatted)})
```

- [ ] **Step 6: Create GetUserChannelRulesTool**

Create `backend/app/agents/triage/tools/get_user_channel_rules.py`:
```python
"""Tool to get user's channel-specific rules and configuration."""

import json
from typing import Any

from app.tools.base import BaseTool, ToolContext


class GetUserChannelRulesTool(BaseTool):
    name = "get_user_channel_rules"
    description = (
        "Get the user's configuration and rules for a specific channel. "
        "Includes channel priority, custom triage instructions, and source rules."
    )
    parameters_schema = {
        "type": "object",
        "properties": {
            "channel_id": {"type": "string", "description": "Slack channel ID"},
        },
        "required": ["channel_id"],
    }
    max_iterations = 1

    async def execute(self, *, context: ToolContext | None = None, **kwargs: Any) -> str:
        if not context or "db" not in context or "user_id" not in context:
            return json.dumps({"error": "Missing db or user_id in context"})

        channel_id = kwargs["channel_id"]
        user_id = context["user_id"]

        from app.services.triage_cache import TriageCacheService

        cache = TriageCacheService()

        # Try cache first
        cached = await cache.get_channel_rules(user_id, channel_id)
        if cached:
            return json.dumps(cached)

        # Cache miss: query DB
        from app.db.repositories.triage import MonitoredChannelRepository

        db = context["db"]
        repo = MonitoredChannelRepository(db)
        channel = await repo.get_by_user_and_channel(user_id, channel_id)

        if not channel:
            return json.dumps({"error": "Channel not found in user's monitored channels"})

        rules = {
            "priority": channel.priority or "medium",
            "triage_instructions": channel.triage_instructions or "",
            "summary_behavior": channel.summary_behavior or "default",
        }

        await cache.set_channel_rules(user_id, channel_id, rules)
        return json.dumps(rules)
```

- [ ] **Step 7: Write unit tests for context-gathering tools**

Create `backend/tests/agents/triage/__init__.py` (empty) and `backend/tests/agents/triage/test_triage_tools.py`:

```python
"""Tests for triage agent tools."""

import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


class TestFetchMessageTool:
    @pytest.mark.asyncio
    async def test_fetches_message_by_ts(self):
        from app.agents.triage.tools.fetch_message import FetchMessageTool

        tool = FetchMessageTool()
        mock_slack = MagicMock()
        mock_slack.client.conversations_history = AsyncMock(return_value={
            "messages": [{"text": "Hello world", "user": "U123", "ts": "123.456"}]
        })

        with patch("app.agents.triage.tools.fetch_message.get_slack_service", return_value=mock_slack):
            result = await tool.execute(channel_id="C123", message_ts="123.456")

        data = json.loads(result)
        assert data["text"] == "Hello world"
        assert data["user"] == "U123"

    @pytest.mark.asyncio
    async def test_returns_error_when_not_found(self):
        from app.agents.triage.tools.fetch_message import FetchMessageTool

        tool = FetchMessageTool()
        mock_slack = MagicMock()
        mock_slack.client.conversations_history = AsyncMock(return_value={"messages": []})

        with patch("app.agents.triage.tools.fetch_message.get_slack_service", return_value=mock_slack):
            result = await tool.execute(channel_id="C123", message_ts="999.999")

        data = json.loads(result)
        assert "error" in data


class TestGetQueuedMessagesTool:
    @pytest.mark.asyncio
    async def test_returns_queued_messages(self):
        from app.agents.triage.tools.get_queued_messages import GetQueuedMessagesTool

        tool = GetQueuedMessagesTool()
        mock_db = AsyncMock()

        mock_item = MagicMock()
        mock_item.id = "item-1"
        mock_item.sender_name = "Felix"
        mock_item.abstract = "Meeting discussion"
        mock_item.action = "summarize_eod"
        mock_item.group_id = None
        mock_item.message_ts = "123.456"
        mock_item.channel_name = "engineering-leads"

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_item]
        mock_db.execute = AsyncMock(return_value=mock_result)

        context = {"db": mock_db, "user_id": "user-1"}
        result = await tool.execute(context=context, channel_id="C123")

        data = json.loads(result)
        assert data["count"] == 1
        assert data["messages"][0]["sender_name"] == "Felix"

    @pytest.mark.asyncio
    async def test_returns_empty_when_no_queued(self):
        from app.agents.triage.tools.get_queued_messages import GetQueuedMessagesTool

        tool = GetQueuedMessagesTool()
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute = AsyncMock(return_value=mock_result)

        context = {"db": mock_db, "user_id": "user-1"}
        result = await tool.execute(context=context, channel_id="C123")

        data = json.loads(result)
        assert data["count"] == 0
```

- [ ] **Step 8: Run tests**

```bash
cd backend && JWT_SECRET=test-secret DATABASE_URL=postgresql+asyncpg://alfred:alfred@localhost:5432/alfred uv run pytest tests/agents/triage/test_triage_tools.py -v
```

- [ ] **Step 9: Commit**

```bash
git add backend/app/agents/triage/tools/ backend/tests/agents/triage/
git commit -m "feat(triage-agent): add context-gathering tools

Tools: fetch_message, fetch_thread, fetch_channel_history,
get_queued_messages, get_user_channel_rules.
Each follows BaseTool pattern with JSON responses."
```

---

## Task 3: Action Tools

**Files:**
- Create: `backend/app/agents/triage/tools/alert_now.py`
- Create: `backend/app/agents/triage/tools/queue_for_digest.py`
- Create: `backend/app/agents/triage/tools/link_messages.py`

- [ ] **Step 1: Create AlertNowTool**

Create `backend/app/agents/triage/tools/alert_now.py`:
```python
"""Tool to send an immediate P0 alert to the user."""

import json
import logging
from datetime import datetime, timezone
from typing import Any

from app.tools.base import BaseTool, ToolContext

logger = logging.getLogger(__name__)


class AlertNowTool(BaseTool):
    name = "alert_now"
    description = (
        "Send an immediate P0 notification to the user via Slack DM. "
        "Use ONLY for truly urgent messages that require immediate action."
    )
    parameters_schema = {
        "type": "object",
        "properties": {
            "abstract": {
                "type": "string",
                "description": "Brief summary of the message (1-2 sentences)",
            },
            "reason": {
                "type": "string",
                "description": "Why this is classified as P0",
            },
            "confidence": {
                "type": "number",
                "description": "Confidence score 0.0-1.0",
            },
        },
        "required": ["abstract", "reason", "confidence"],
    }
    max_iterations = 1

    async def execute(self, *, context: ToolContext | None = None, **kwargs: Any) -> str:
        if not context or "db" not in context or "user_id" not in context:
            return json.dumps({"error": "Missing db or user_id in context"})

        # These are injected into context by the agent runner
        state = context.get("agent_state", {})
        user_id = context["user_id"]
        db = context["db"]

        abstract = kwargs["abstract"]
        reason = kwargs["reason"]
        confidence = float(kwargs.get("confidence", 0.8))

        from app.db.repositories.triage import TriageClassificationRepository
        from app.db.models.triage import TriageClassification

        repo = TriageClassificationRepository(db)

        # Create classification record
        classification = TriageClassification(
            user_id=user_id,
            sender_slack_id=state.get("sender_slack_id", ""),
            sender_name=state.get("sender_name", ""),
            channel_id=state.get("channel_id", ""),
            channel_name=state.get("channel_name", ""),
            message_ts=state.get("message_ts", ""),
            thread_ts=state.get("thread_ts"),
            slack_permalink=state.get("slack_permalink", ""),
            action="notify_now",
            confidence=confidence,
            classification_reason=reason,
            abstract=abstract,
            classification_path=state.get("event_type", "channel"),
            queued_for_digest=False,
            last_alerted_at=datetime.now(timezone.utc),
            alert_count=1,
        )
        classification = await repo.create(classification)
        await db.flush()

        # Send Slack DM
        from app.db.repositories import UserRepository
        from app.services.slack import get_slack_service
        from app.services.notifications import NotificationService

        user_repo = UserRepository(db)
        user = await user_repo.get(user_id)
        if user and user.slack_user_id:
            slack = get_slack_service()
            sender = state.get("sender_name") or state.get("sender_slack_id", "Someone")
            channel_name = state.get("channel_name", "")
            channel_info = f" in #{channel_name}" if channel_name else ""
            permalink = state.get("slack_permalink", "")
            permalink_text = f"\n<{permalink}|View message>" if permalink else ""

            dm_text = (
                f"*P0 -- Urgent message from {sender}{channel_info}*\n"
                f"{abstract}{permalink_text}"
            )
            try:
                await slack.send_message(channel=user.slack_user_id, text=dm_text)
            except Exception:
                logger.exception("Failed to send P0 Slack DM")

            # SSE notification
            notification_service = NotificationService(db)
            await notification_service.publish(
                user_id=user_id,
                event_type="triage.urgent",
                data={
                    "classification_id": str(classification.id),
                    "sender_slack_id": state.get("sender_slack_id", ""),
                    "sender_name": sender,
                    "channel_id": state.get("channel_id", ""),
                    "priority_level": "p0",
                    "abstract": abstract,
                    "slack_permalink": permalink,
                },
            )

        return json.dumps({
            "status": "alerted",
            "classification_id": str(classification.id),
        })
```

- [ ] **Step 2: Create QueueForDigestTool**

Create `backend/app/agents/triage/tools/queue_for_digest.py`:
```python
"""Tool to queue a message for later digest delivery."""

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from app.tools.base import BaseTool, ToolContext

logger = logging.getLogger(__name__)


class QueueForDigestTool(BaseTool):
    name = "queue_for_digest"
    description = (
        "Queue a message for later digest delivery. Provide the priority "
        "(P1, P2, or P3) and a brief abstract."
    )
    parameters_schema = {
        "type": "object",
        "properties": {
            "abstract": {
                "type": "string",
                "description": "Brief summary of the message (1-2 sentences)",
            },
            "reason": {
                "type": "string",
                "description": "Why this priority was chosen",
            },
            "confidence": {
                "type": "number",
                "description": "Confidence score 0.0-1.0",
            },
            "priority": {
                "type": "string",
                "enum": ["P1", "P2", "P3"],
                "description": "Priority: P1 (hours), P2 (EOD), P3 (ignore)",
            },
        },
        "required": ["abstract", "reason", "confidence", "priority"],
    }
    max_iterations = 1

    async def execute(self, *, context: ToolContext | None = None, **kwargs: Any) -> str:
        if not context or "db" not in context or "user_id" not in context:
            return json.dumps({"error": "Missing db or user_id in context"})

        state = context.get("agent_state", {})
        user_id = context["user_id"]
        db = context["db"]

        abstract = kwargs["abstract"]
        reason = kwargs["reason"]
        confidence = float(kwargs.get("confidence", 0.7))
        priority = kwargs["priority"].upper()

        # Map priority to action
        priority_to_action = {
            "P1": "summarize_next",
            "P2": "summarize_eod",
            "P3": "ignore",
        }
        action = priority_to_action.get(priority, "summarize_eod")

        # Set delivery parameters based on priority
        now = datetime.now(timezone.utc)
        p1_max_wait = state.get("p1_max_wait_minutes", 60)
        p1_settle = state.get("p1_settled_threshold_minutes", 30)

        if priority == "P1":
            deliver_by = now + timedelta(minutes=p1_max_wait)
            settled_threshold = p1_settle
            queued = True
        elif priority == "P2":
            # EOD delivery — deliver_by is set to user's EOD time
            # For now, set to end of day (handled by delivery checker)
            deliver_by = None  # Delivery checker uses eod_review_time
            settled_threshold = None
            queued = True
        else:  # P3
            deliver_by = None
            settled_threshold = None
            queued = False  # P3 not actively delivered

        from app.db.repositories.triage import TriageClassificationRepository
        from app.db.models.triage import TriageClassification

        repo = TriageClassificationRepository(db)
        classification = TriageClassification(
            user_id=user_id,
            sender_slack_id=state.get("sender_slack_id", ""),
            sender_name=state.get("sender_name", ""),
            channel_id=state.get("channel_id", ""),
            channel_name=state.get("channel_name", ""),
            message_ts=state.get("message_ts", ""),
            thread_ts=state.get("thread_ts"),
            slack_permalink=state.get("slack_permalink", ""),
            action=action,
            confidence=confidence,
            classification_reason=reason,
            abstract=abstract,
            classification_path=state.get("event_type", "channel"),
            queued_for_digest=queued,
            deliver_by=deliver_by,
            settled_threshold=settled_threshold,
            last_related_activity_at=now,
            group_id=state.get("pending_group_id"),  # Set by link_messages if called
        )
        classification = await repo.create(classification)
        await db.flush()

        return json.dumps({
            "status": "queued",
            "classification_id": str(classification.id),
            "priority": priority,
            "action": action,
            "deliver_by": deliver_by.isoformat() if deliver_by else None,
        })
```

- [ ] **Step 3: Create LinkMessagesTool**

Create `backend/app/agents/triage/tools/link_messages.py`:
```python
"""Tool to link the current message to an existing queued message."""

import json
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from app.tools.base import BaseTool, ToolContext

logger = logging.getLogger(__name__)


class LinkMessagesTool(BaseTool):
    name = "link_messages"
    description = (
        "Link this message to an existing queued message because they are related. "
        "Both messages will get the same group_id. The group's delivery timing "
        "will be upgraded to match the higher priority. "
        "You must still call queue_for_digest after this."
    )
    parameters_schema = {
        "type": "object",
        "properties": {
            "existing_message_id": {
                "type": "string",
                "description": "ID of the existing queued message to link to",
            },
            "priority": {
                "type": "string",
                "enum": ["P1", "P2", "P3"],
                "description": "Priority of the new message (group uses highest)",
            },
        },
        "required": ["existing_message_id", "priority"],
    }
    max_iterations = 1

    async def execute(self, *, context: ToolContext | None = None, **kwargs: Any) -> str:
        if not context or "db" not in context:
            return json.dumps({"error": "Missing db in context"})

        existing_id = kwargs["existing_message_id"]
        priority = kwargs["priority"].upper()
        db = context["db"]

        from sqlalchemy import select, update
        from app.db.models.triage import TriageClassification

        # Get existing message
        result = await db.execute(
            select(TriageClassification)
            .where(TriageClassification.id == existing_id)
        )
        existing = result.scalar_one_or_none()
        if not existing:
            return json.dumps({"error": f"Message {existing_id} not found"})

        # Determine group_id: use existing group or create new one
        group_id = existing.group_id or str(uuid.uuid4())

        # Update existing message with group_id if not already set
        if not existing.group_id:
            await db.execute(
                update(TriageClassification)
                .where(TriageClassification.id == existing_id)
                .values(group_id=group_id)
            )

        # Upgrade group delivery parameters if new priority is higher
        now = datetime.now(timezone.utc)
        p1_max_wait = context.get("agent_state", {}).get("p1_max_wait_minutes", 60)
        p1_settle = context.get("agent_state", {}).get("p1_settled_threshold_minutes", 30)

        if priority == "P1":
            new_deliver_by = now + timedelta(minutes=p1_max_wait)
            new_settle = p1_settle

            # Update all messages in this group to P1 timing
            await db.execute(
                update(TriageClassification)
                .where(TriageClassification.group_id == group_id)
                .values(
                    deliver_by=new_deliver_by,
                    settled_threshold=new_settle,
                    last_related_activity_at=now,
                )
            )

        # Update last_related_activity_at for the group
        await db.execute(
            update(TriageClassification)
            .where(TriageClassification.group_id == group_id)
            .values(last_related_activity_at=now)
        )
        await db.flush()

        # Store group_id in context so queue_for_digest can use it
        if "agent_state" in context:
            context["agent_state"]["pending_group_id"] = group_id

        return json.dumps({
            "status": "linked",
            "group_id": group_id,
            "existing_message_id": existing_id,
        })
```

- [ ] **Step 4: Add tests for action tools**

Append to `backend/tests/agents/triage/test_triage_tools.py`:

```python
class TestAlertNowTool:
    @pytest.mark.asyncio
    async def test_creates_classification_and_sends_dm(self):
        from app.agents.triage.tools.alert_now import AlertNowTool

        tool = AlertNowTool()
        mock_db = AsyncMock()
        mock_classification = MagicMock()
        mock_classification.id = "class-1"

        mock_repo = MagicMock()
        mock_repo.create = AsyncMock(return_value=mock_classification)

        mock_user = MagicMock()
        mock_user.slack_user_id = "U_USER"

        context = {
            "db": mock_db,
            "user_id": "user-1",
            "agent_state": {
                "sender_slack_id": "U_SENDER",
                "sender_name": "Alice",
                "channel_id": "C123",
                "channel_name": "engineering",
                "message_ts": "123.456",
                "event_type": "channel",
            },
        }

        with patch("app.agents.triage.tools.alert_now.TriageClassificationRepository", return_value=mock_repo):
            with patch("app.agents.triage.tools.alert_now.UserRepository") as MockUserRepo:
                MockUserRepo.return_value.get = AsyncMock(return_value=mock_user)
                with patch("app.agents.triage.tools.alert_now.get_slack_service") as mock_slack:
                    mock_slack.return_value.send_message = AsyncMock()
                    with patch("app.agents.triage.tools.alert_now.NotificationService") as MockNotif:
                        MockNotif.return_value.publish = AsyncMock()
                        result = await tool.execute(
                            context=context,
                            abstract="Production is down",
                            reason="Active incident",
                            confidence=0.95,
                        )

        data = json.loads(result)
        assert data["status"] == "alerted"
        assert data["classification_id"] == "class-1"


class TestQueueForDigestTool:
    @pytest.mark.asyncio
    async def test_queues_p1_with_delivery_params(self):
        from app.agents.triage.tools.queue_for_digest import QueueForDigestTool

        tool = QueueForDigestTool()
        mock_db = AsyncMock()
        mock_classification = MagicMock()
        mock_classification.id = "class-2"

        mock_repo = MagicMock()
        mock_repo.create = AsyncMock(return_value=mock_classification)

        context = {
            "db": mock_db,
            "user_id": "user-1",
            "agent_state": {
                "sender_slack_id": "U_SENDER",
                "channel_id": "C123",
                "message_ts": "123.456",
                "event_type": "channel",
                "p1_max_wait_minutes": 60,
                "p1_settled_threshold_minutes": 30,
            },
        }

        with patch("app.agents.triage.tools.queue_for_digest.TriageClassificationRepository", return_value=mock_repo):
            result = await tool.execute(
                context=context,
                abstract="Meeting request",
                reason="Direct ask needing response",
                confidence=0.8,
                priority="P1",
            )

        data = json.loads(result)
        assert data["status"] == "queued"
        assert data["priority"] == "P1"
        assert data["action"] == "summarize_next"
        assert data["deliver_by"] is not None


class TestLinkMessagesTool:
    @pytest.mark.asyncio
    async def test_links_to_existing_message(self):
        from app.agents.triage.tools.link_messages import LinkMessagesTool

        tool = LinkMessagesTool()
        mock_db = AsyncMock()

        mock_existing = MagicMock()
        mock_existing.group_id = None

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_existing
        mock_db.execute = AsyncMock(return_value=mock_result)

        context = {
            "db": mock_db,
            "user_id": "user-1",
            "agent_state": {"p1_max_wait_minutes": 60, "p1_settled_threshold_minutes": 30},
        }

        result = await tool.execute(
            context=context,
            existing_message_id="existing-1",
            priority="P1",
        )

        data = json.loads(result)
        assert data["status"] == "linked"
        assert data["group_id"] is not None
```

- [ ] **Step 5: Run tests**

```bash
cd backend && JWT_SECRET=test-secret DATABASE_URL=postgresql+asyncpg://alfred:alfred@localhost:5432/alfred uv run pytest tests/agents/triage/test_triage_tools.py -v
```

- [ ] **Step 6: Commit**

```bash
git add backend/app/agents/triage/tools/alert_now.py backend/app/agents/triage/tools/queue_for_digest.py backend/app/agents/triage/tools/link_messages.py backend/tests/agents/triage/test_triage_tools.py
git commit -m "feat(triage-agent): add action tools

Tools: alert_now (P0 notification), queue_for_digest (P1/P2/P3),
link_messages (group related messages). Each creates/updates
TriageClassification records with delivery parameters."
```

---

## Task 4: Agent Graph and Nodes

**Files:**
- Create: `backend/app/agents/triage/graph.py`
- Create: `backend/app/agents/triage/nodes.py`
- Create: `backend/app/agents/triage/agent.py`

- [ ] **Step 1: Create node functions**

Create `backend/app/agents/triage/nodes.py`. This follows the same pattern as `backend/app/agents/nodes.py` but simpler:

```python
"""Node functions for the triage agent graph."""

import json
import logging
from typing import Any

from app.agents.triage.prompt import build_system_prompt, MAX_TOOL_CALLS
from app.agents.triage.state import TriageAgentState
from app.core.llm import LLMMessage, get_llm_provider
from app.core.config import get_settings

logger = logging.getLogger(__name__)


async def setup_node(state: TriageAgentState, config: dict) -> dict:
    """Initialize the agent with system prompt and prepare for LLM call."""
    system_prompt = build_system_prompt(
        sensitivity=state["sensitivity"],
        custom_rules=state.get("custom_rules"),
        p0_definition=state.get("p0_definition"),
        p1_definition=state.get("p1_definition"),
        p2_definition=state.get("p2_definition"),
        p3_definition=state.get("p3_definition"),
    )

    # Build initial user message with message reference info
    channel_id = state["channel_id"]
    message_ts = state["message_ts"]
    thread_ts = state.get("thread_ts")
    sender = state.get("sender_slack_id", "unknown")
    event_type = state.get("event_type", "channel")

    user_msg = (
        f"Classify this Slack message.\n\n"
        f"Channel: {channel_id}\n"
        f"Message timestamp: {message_ts}\n"
        f"Thread: {thread_ts or 'none (top-level message)'}\n"
        f"Sender: {sender}\n"
        f"Event type: {event_type}\n\n"
        f"Start by calling fetch_message to get the message text, "
        f"then call get_queued_messages to check for related messages."
    )

    return {
        "llm_messages": [
            LLMMessage(role="system", content=system_prompt),
            LLMMessage(role="user", content=user_msg),
        ],
        "tool_iteration": 0,
        "tool_call_count": 0,
        "tool_calls": None,
        "action_taken": None,
        "classification_id": None,
        "error": None,
        "needs_review": False,
    }


async def llm_node(state: TriageAgentState, config: dict) -> dict:
    """Call the LLM with current messages and tool definitions."""
    configurable = config.get("configurable", {})
    tool_registry = configurable.get("tool_registry")

    settings = get_settings()
    provider = get_llm_provider(
        settings.triage_classification_model,
        location=settings.triage_vertex_location or None,
    )

    tool_defs = tool_registry.get_definitions() if tool_registry else []

    try:
        response = await provider.generate_with_tools(
            messages=state["llm_messages"],
            tools=tool_defs,
            temperature=0.1,
            max_tokens=4096,
        )
    except Exception as e:
        logger.exception("Triage agent LLM call failed")
        return {"error": f"LLM call failed: {str(e)}"}

    # Append assistant response to messages
    new_messages = list(state["llm_messages"])
    new_messages.append(LLMMessage(
        role="assistant",
        content=response.content or "",
        tool_calls=response.tool_calls,
    ))

    return {
        "llm_messages": new_messages,
        "tool_calls": response.tool_calls,
        "tool_iteration": state["tool_iteration"] + 1,
    }


async def tool_node(state: TriageAgentState, config: dict) -> dict:
    """Execute tool calls from the LLM response."""
    configurable = config.get("configurable", {})
    tool_registry = configurable.get("tool_registry")
    db = configurable.get("db")
    user_id = configurable.get("user_id")

    tool_calls = state.get("tool_calls", [])
    if not tool_calls:
        return {}

    new_messages = list(state["llm_messages"])
    tool_call_count = state.get("tool_call_count", 0)
    action_taken = state.get("action_taken")
    classification_id = state.get("classification_id")

    # Build tool context
    tool_context = {
        "db": db,
        "user_id": user_id,
        "agent_state": {
            "sender_slack_id": state.get("sender_slack_id", ""),
            "sender_name": "",  # Will be populated from fetch_message
            "channel_id": state.get("channel_id", ""),
            "channel_name": "",
            "message_ts": state.get("message_ts", ""),
            "thread_ts": state.get("thread_ts"),
            "slack_permalink": "",
            "event_type": state.get("event_type", "channel"),
            "p1_max_wait_minutes": state.get("p1_max_wait_minutes", 60),
            "p1_settled_threshold_minutes": state.get("p1_settled_threshold_minutes", 30),
        },
    }

    for tc in tool_calls:
        tool = tool_registry.get(tc.name) if tool_registry else None
        if not tool:
            result = json.dumps({"error": f"Unknown tool: {tc.name}"})
        else:
            tool_call_count += 1
            if tool_call_count > MAX_TOOL_CALLS:
                result = json.dumps({
                    "error": f"Tool call limit ({MAX_TOOL_CALLS}) exceeded. "
                    "Classify with available context."
                })
            else:
                try:
                    result = await tool.execute(context=tool_context, **tc.arguments)
                except Exception as e:
                    logger.exception(f"Triage tool {tc.name} failed")
                    result = json.dumps({"error": f"Tool {tc.name} failed: {str(e)}"})

        # Check if action was taken
        try:
            result_data = json.loads(result)
            if result_data.get("status") == "alerted":
                action_taken = "alert_now"
                classification_id = result_data.get("classification_id")
            elif result_data.get("status") == "queued":
                action_taken = "queue_for_digest"
                classification_id = result_data.get("classification_id")
        except (json.JSONDecodeError, TypeError):
            pass

        new_messages.append(LLMMessage(
            role="tool",
            content=result,
            tool_call_id=tc.id,
        ))

    needs_review = tool_call_count >= MAX_TOOL_CALLS

    return {
        "llm_messages": new_messages,
        "tool_calls": None,
        "tool_call_count": tool_call_count,
        "action_taken": action_taken,
        "classification_id": classification_id,
        "needs_review": needs_review,
    }


def route_after_llm(state: TriageAgentState) -> str:
    """Route after LLM response: tool calls or done."""
    if state.get("error"):
        return "end"
    if state.get("action_taken"):
        return "end"
    if state.get("tool_calls"):
        return "tool_node"
    # No tool calls and no action — agent responded with text (shouldn't happen)
    return "end"


def route_after_tool(state: TriageAgentState) -> str:
    """Route after tool execution: back to LLM or done."""
    if state.get("action_taken"):
        return "end"
    if state.get("needs_review"):
        return "end"
    return "llm_node"
```

- [ ] **Step 2: Create graph**

Create `backend/app/agents/triage/graph.py`:
```python
"""LangGraph StateGraph for the triage agent."""

from langgraph.graph import END, StateGraph

from app.agents.triage.nodes import (
    llm_node,
    route_after_llm,
    route_after_tool,
    setup_node,
    tool_node,
)
from app.agents.triage.state import TriageAgentState


def create_triage_graph() -> StateGraph:
    """Create the triage agent graph.

    Flow: setup -> llm_node -> (tool_calls? -> tool_node -> llm_node [cycle], else -> END)
    """
    builder = StateGraph(TriageAgentState)

    builder.add_node("setup", setup_node)
    builder.add_node("llm_node", llm_node)
    builder.add_node("tool_node", tool_node)

    builder.set_entry_point("setup")
    builder.add_edge("setup", "llm_node")

    builder.add_conditional_edges("llm_node", route_after_llm, {
        "tool_node": "tool_node",
        "end": END,
    })

    builder.add_conditional_edges("tool_node", route_after_tool, {
        "llm_node": "llm_node",
        "end": END,
    })

    return builder.compile()
```

- [ ] **Step 3: Create agent class**

Create `backend/app/agents/triage/agent.py`:
```python
"""Triage agent — classifies Slack messages using tools."""

import logging
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.triage.graph import create_triage_graph
from app.agents.triage.state import TriageAgentState
from app.agents.triage.tools import get_triage_tool_registry

logger = logging.getLogger(__name__)


class TriageAgent:
    """Agent that classifies Slack messages using tools for context gathering.

    Usage:
        agent = TriageAgent(db)
        result = await agent.classify(
            user_id="...",
            channel_id="C123",
            message_ts="123.456",
            ...
        )
    """

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.graph = create_triage_graph()
        self.tool_registry = get_triage_tool_registry()

    async def classify(
        self,
        user_id: str,
        channel_id: str,
        message_ts: str,
        sender_slack_id: str,
        event_type: str = "channel",
        thread_ts: str | None = None,
        bot_id: str | None = None,
        message_text_fallback: str = "",
        sensitivity: str = "medium",
        custom_rules: str | None = None,
        p0_definition: str | None = None,
        p1_definition: str | None = None,
        p2_definition: str | None = None,
        p3_definition: str | None = None,
        p1_max_wait_minutes: int = 60,
        p1_settled_threshold_minutes: int = 30,
        eod_review_time: str = "17:30",
    ) -> dict[str, Any]:
        """Classify a message using the triage agent.

        Returns:
            Dict with action_taken, classification_id, error, needs_review
        """
        initial_state: TriageAgentState = {
            "user_id": user_id,
            "channel_id": channel_id,
            "message_ts": message_ts,
            "thread_ts": thread_ts,
            "sender_slack_id": sender_slack_id,
            "event_type": event_type,
            "bot_id": bot_id,
            "message_text_fallback": message_text_fallback,
            "sensitivity": sensitivity,
            "custom_rules": custom_rules,
            "p0_definition": p0_definition,
            "p1_definition": p1_definition,
            "p2_definition": p2_definition,
            "p3_definition": p3_definition,
            "p1_max_wait_minutes": p1_max_wait_minutes,
            "p1_settled_threshold_minutes": p1_settled_threshold_minutes,
            "eod_review_time": eod_review_time,
            "llm_messages": [],
            "tool_calls": None,
            "tool_iteration": 0,
            "tool_call_count": 0,
            "action_taken": None,
            "classification_id": None,
            "error": None,
            "needs_review": False,
        }

        config = {
            "configurable": {
                "db": self.db,
                "user_id": user_id,
                "tool_registry": self.tool_registry,
            },
            "recursion_limit": 25,
        }

        try:
            final_state = await self.graph.ainvoke(initial_state, config)
            return {
                "action_taken": final_state.get("action_taken"),
                "classification_id": final_state.get("classification_id"),
                "error": final_state.get("error"),
                "needs_review": final_state.get("needs_review", False),
                "tool_iterations": final_state.get("tool_iteration", 0),
                "tool_call_count": final_state.get("tool_call_count", 0),
            }
        except Exception as e:
            logger.exception("Triage agent graph execution failed")
            return {
                "action_taken": None,
                "classification_id": None,
                "error": str(e),
                "needs_review": True,
                "tool_iterations": 0,
                "tool_call_count": 0,
            }
```

- [ ] **Step 4: Commit**

```bash
git add backend/app/agents/triage/graph.py backend/app/agents/triage/nodes.py backend/app/agents/triage/agent.py
git commit -m "feat(triage-agent): add graph, nodes, and agent class

LangGraph StateGraph: setup -> llm_node -> tool_node cycle.
TriageAgent.classify() is the main entry point.
Follows existing Alfred agent patterns."
```

---

## Task 5: Feature Flag and Worker Task

**Files:**
- Create: `backend/alembic/versions/057_add_agent_triage_flag.py`
- Modify: `backend/app/db/models/triage.py` — add `use_agent_triage` to TriageUserSettings
- Modify: `backend/app/worker/tasks.py` — add `run_triage_agent` task, modify `prefilter_triage_message`
- Modify: `backend/app/worker/main.py` — register new task

- [ ] **Step 1: Add feature flag to model**

In `backend/app/db/models/triage.py`, add to TriageUserSettings after the P1 timing columns:
```python
    # --- Feature flag for agent-driven triage ---
    use_agent_triage: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
```

- [ ] **Step 2: Create migration**

Create `backend/alembic/versions/057_add_agent_triage_flag.py`:
```python
"""add agent triage feature flag

Revision ID: 057
Revises: 056
Create Date: 2026-06-07
"""

from alembic import op
import sqlalchemy as sa

revision = "057"
down_revision = "056"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("triage_user_settings", sa.Column("use_agent_triage", sa.Boolean(), server_default="false", nullable=False))


def downgrade() -> None:
    op.drop_column("triage_user_settings", "use_agent_triage")
```

- [ ] **Step 3: Add run_triage_agent task**

In `backend/app/worker/tasks.py`, add:
```python
async def run_triage_agent(
    ctx: dict,
    user_id: str,
    event_type: str,
    channel_id: str,
    sender_slack_id: str,
    message_ts: str,
    thread_ts: str | None = None,
    bot_id: str | None = None,
) -> dict:
    """Run the triage agent to classify a message.

    This replaces process_triage_job for users with use_agent_triage=True.
    """
    from app.agents.triage.agent import TriageAgent
    from app.db.repositories.triage import TriageUserSettingsRepository

    async with get_db_session() as db:
        # Get user settings for agent config
        settings_repo = TriageUserSettingsRepository(db)
        settings = await settings_repo.get_by_user_id(user_id)

        agent = TriageAgent(db)
        result = await agent.classify(
            user_id=user_id,
            channel_id=channel_id,
            message_ts=message_ts,
            sender_slack_id=sender_slack_id,
            event_type=event_type,
            thread_ts=thread_ts,
            bot_id=bot_id,
            sensitivity=settings.sensitivity if settings else "medium",
            custom_rules=settings.custom_classification_rules if settings else None,
            p0_definition=settings.p0_definition if settings else None,
            p1_definition=settings.p1_definition if settings else None,
            p2_definition=settings.p2_definition if settings else None,
            p3_definition=settings.p3_definition if settings else None,
            p1_max_wait_minutes=settings.p1_max_wait_minutes if settings else 60,
            p1_settled_threshold_minutes=settings.p1_settled_threshold_minutes if settings else 30,
            eod_review_time=settings.eod_review_time if settings else "17:30",
        )

        if result.get("error") and not result.get("action_taken"):
            # Agent failed — check retry count
            retry_count = ctx.get("job_try", 1)
            if retry_count >= 3:
                # Max retries — store as P2 with needs_review
                from app.db.models.triage import TriageClassification
                from app.db.repositories.triage import TriageClassificationRepository

                repo = TriageClassificationRepository(db)
                classification = TriageClassification(
                    user_id=user_id,
                    sender_slack_id=sender_slack_id,
                    channel_id=channel_id,
                    message_ts=message_ts,
                    thread_ts=thread_ts,
                    action="summarize_eod",
                    confidence=0.0,
                    classification_reason=f"Agent failed after {retry_count} retries: {result['error']}",
                    abstract="Message pending review (agent classification failed)",
                    classification_path=event_type,
                    queued_for_digest=True,
                    needs_review=True,
                    retry_count=retry_count,
                )
                await repo.create(classification)
                await db.commit()
                return {"status": "fallback", "error": result["error"]}
            else:
                # Requeue for retry
                raise Exception(f"Triage agent failed: {result['error']}")

        await db.commit()
        return {
            "status": "classified",
            "action_taken": result.get("action_taken"),
            "classification_id": result.get("classification_id"),
            "tool_iterations": result.get("tool_iterations"),
        }
```

- [ ] **Step 4: Modify prefilter_triage_message to check feature flag**

In the `prefilter_triage_message` function in `tasks.py`, update the fan-out section to check the feature flag:

```python
    # Fan out: enqueue one triage job per applicable user
    # Use agent-driven triage if user has feature flag enabled
    from app.db.repositories.triage import TriageUserSettingsRepository

    pool = await get_redis_pool()

    async with get_db_session() as db:
        settings_repo = TriageUserSettingsRepository(db)

        for user_id in applicable_users:
            settings = await settings_repo.get_by_user_id(user_id)
            use_agent = settings.use_agent_triage if settings else False

            if use_agent:
                await pool.enqueue_job(
                    "run_triage_agent",
                    user_id=user_id,
                    event_type=event_type,
                    channel_id=channel_id,
                    sender_slack_id=sender_slack_id,
                    message_ts=message_ts,
                    thread_ts=thread_ts,
                    bot_id=bot_id,
                )
            else:
                await pool.enqueue_job(
                    "process_triage_job",
                    user_id=user_id,
                    event_type=event_type,
                    channel_id=channel_id,
                    sender_slack_id=sender_slack_id,
                    message_ts=message_ts,
                    thread_ts=thread_ts,
                    message_text=message_text,
                    bot_id=bot_id,
                )
```

- [ ] **Step 5: Register in worker**

In `backend/app/worker/main.py`, add `run_triage_agent` to the functions list and import.

- [ ] **Step 6: Commit**

```bash
git add backend/app/db/models/triage.py backend/alembic/versions/057_add_agent_triage_flag.py backend/app/worker/tasks.py backend/app/worker/main.py
git commit -m "feat(triage-agent): add feature flag and worker task

use_agent_triage flag on TriageUserSettings controls per-user switchover.
prefilter_triage_message checks flag and routes to run_triage_agent or
process_triage_job accordingly. Agent failures requeue up to 3 times,
then fallback to P2 with needs_review."
```

---

## Task 6: Integration Tests

**Files:**
- Create: `backend/tests/agents/triage/test_triage_agent.py`

- [ ] **Step 1: Write agent integration test**

Create `backend/tests/agents/triage/test_triage_agent.py`:

```python
"""Integration tests for the triage agent."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import json


class TestTriageAgentClassify:
    @pytest.mark.asyncio
    async def test_agent_returns_result_structure(self):
        """Verify agent returns expected result keys."""
        from app.agents.triage.agent import TriageAgent

        mock_db = AsyncMock()

        # Mock the graph execution
        with patch.object(TriageAgent, "__init__", return_value=None):
            agent = TriageAgent.__new__(TriageAgent)
            agent.db = mock_db
            agent.tool_registry = MagicMock()

            mock_graph = AsyncMock()
            mock_graph.ainvoke = AsyncMock(return_value={
                "action_taken": "queue_for_digest",
                "classification_id": "test-id",
                "error": None,
                "needs_review": False,
                "tool_iteration": 3,
                "tool_call_count": 4,
            })
            agent.graph = mock_graph

            result = await agent.classify(
                user_id="user-1",
                channel_id="C123",
                message_ts="123.456",
                sender_slack_id="U_SENDER",
            )

        assert "action_taken" in result
        assert "classification_id" in result
        assert "error" in result
        assert "needs_review" in result
        assert result["action_taken"] == "queue_for_digest"

    @pytest.mark.asyncio
    async def test_agent_handles_graph_error(self):
        """Agent should return error dict on graph failure, not raise."""
        from app.agents.triage.agent import TriageAgent

        mock_db = AsyncMock()

        with patch.object(TriageAgent, "__init__", return_value=None):
            agent = TriageAgent.__new__(TriageAgent)
            agent.db = mock_db
            agent.tool_registry = MagicMock()

            mock_graph = AsyncMock()
            mock_graph.ainvoke = AsyncMock(side_effect=Exception("LLM timeout"))
            agent.graph = mock_graph

            result = await agent.classify(
                user_id="user-1",
                channel_id="C123",
                message_ts="123.456",
                sender_slack_id="U_SENDER",
            )

        assert result["error"] is not None
        assert result["needs_review"] is True
        assert result["action_taken"] is None


class TestTriageToolRegistry:
    def test_registry_has_all_tools(self):
        """Verify all 8 tools are registered."""
        from app.agents.triage.tools import get_triage_tool_registry

        registry = get_triage_tool_registry()
        expected_tools = [
            "fetch_message",
            "fetch_thread",
            "fetch_channel_history",
            "get_queued_messages",
            "get_user_channel_rules",
            "alert_now",
            "queue_for_digest",
            "link_messages",
        ]
        for tool_name in expected_tools:
            assert registry.get(tool_name) is not None, f"Missing tool: {tool_name}"

    def test_registry_returns_definitions(self):
        """Verify tool definitions are generated."""
        from app.agents.triage.tools import get_triage_tool_registry

        registry = get_triage_tool_registry()
        defs = registry.get_definitions()
        assert len(defs) == 8
        names = {d.name for d in defs}
        assert "fetch_message" in names
        assert "alert_now" in names
```

- [ ] **Step 2: Run tests**

```bash
cd backend && JWT_SECRET=test-secret DATABASE_URL=postgresql+asyncpg://alfred:alfred@localhost:5432/alfred uv run pytest tests/agents/triage/ -v
```

- [ ] **Step 3: Commit**

```bash
git add backend/tests/agents/triage/
git commit -m "test(triage-agent): add integration and tool registry tests"
```

---

## Task 7: Deploy and Verify

- [ ] **Step 1: Run all tests**

```bash
cd backend && JWT_SECRET=test-secret DATABASE_URL=postgresql+asyncpg://alfred:alfred@localhost:5432/alfred uv run pytest tests/agents/triage/ tests/services/test_triage_prefilter.py tests/services/test_triage_cache.py tests/test_tools.py -v
```

- [ ] **Step 2: Push**

```bash
git push origin slack-triage-refactor-3
```

- [ ] **Step 3: Deploy to production**

```bash
gcloud compute ssh --zone "us-central1-c" "alfred-pa" --project "tyler-knotek-e1ltzltz-af40" --command "cd /opt/alfred && sudo git pull && sudo docker compose -f docker-compose.prod.yml up -d --build backend worker"
```

- [ ] **Step 4: Run migration**

The migration (057) will run automatically via the migrate container.

- [ ] **Step 5: Enable feature flag for test user**

```sql
UPDATE triage_user_settings SET use_agent_triage = true WHERE user_id = '<your_user_id>';
```

- [ ] **Step 6: Verify agent processing**

Send a test message in a monitored channel and check worker logs:
```bash
gcloud compute ssh --zone "us-central1-c" "alfred-pa" --command "sudo docker logs alfred-worker-1 --tail=50 2>&1 | grep -i triage"
```

Look for: `"Pre-filter: message ... queued for 1 users"` followed by agent tool calls.

---

## Transition Notes

- **Feature flag** `use_agent_triage` on `TriageUserSettings` controls per-user switchover
- Default is `false` — all users stay on old pipeline until explicitly enabled
- Enable for one user first, monitor for 24 hours, then roll out
- The old `process_triage_job` and `TriagePipeline` remain active for users without the flag
- Plan 3 (Delivery Checker + Digest Subagent) builds on the agent's output
- Plan 4 (Cleanup) removes old pipeline code after full rollout
