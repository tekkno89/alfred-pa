"""Integration tests for the triage agent: classify, routing, setup, and registry."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.llm import LLMMessage


# ---------------------------------------------------------------------------
# TestTriageAgentClassify
# ---------------------------------------------------------------------------


class TestTriageAgentClassify:
    """Verify TriageAgent.classify returns the expected result structure."""

    @pytest.mark.asyncio
    async def test_agent_returns_result_structure(self):
        """classify() should return dict with all expected keys on success."""
        from app.agents.triage.agent import TriageAgent

        db = AsyncMock()
        agent = TriageAgent(db)

        # Replace the compiled graph with a mock that returns a "successful" state
        mock_graph = AsyncMock()
        mock_graph.ainvoke.return_value = {
            "action_taken": "queued",
            "classification_id": "cls-123",
            "error": None,
            "needs_review": False,
            "tool_iteration": 2,
            "tool_call_count": 4,
        }
        agent.graph = mock_graph

        result = await agent.classify(
            user_id="u1",
            channel_id="C111",
            message_ts="1234.5678",
            sender_slack_id="U999",
        )

        expected_keys = {
            "action_taken",
            "classification_id",
            "error",
            "needs_review",
            "tool_iterations",
            "tool_call_count",
        }
        assert set(result.keys()) == expected_keys
        assert result["action_taken"] == "queued"
        assert result["classification_id"] == "cls-123"
        assert result["error"] is None
        assert result["needs_review"] is False
        assert result["tool_iterations"] == 2
        assert result["tool_call_count"] == 4

    @pytest.mark.asyncio
    async def test_agent_handles_graph_error(self):
        """classify() should return error dict on graph failure, not raise."""
        from app.agents.triage.agent import TriageAgent

        db = AsyncMock()
        agent = TriageAgent(db)

        mock_graph = AsyncMock()
        mock_graph.ainvoke.side_effect = RuntimeError("LLM boom")
        agent.graph = mock_graph

        result = await agent.classify(
            user_id="u1",
            channel_id="C111",
            message_ts="1234.5678",
            sender_slack_id="U999",
        )

        assert result["action_taken"] is None
        assert result["classification_id"] is None
        assert "Agent execution failed" in result["error"]
        assert result["needs_review"] is True
        assert result["tool_iterations"] == 0
        assert result["tool_call_count"] == 0


# ---------------------------------------------------------------------------
# TestTriageToolRegistry
# ---------------------------------------------------------------------------


class TestTriageToolRegistry:
    """Verify the triage tool registry has all 8 tools."""

    def test_registry_has_all_tools(self):
        """All 8 triage tools should be registered."""
        from app.agents.triage.tools import get_triage_tool_registry

        registry = get_triage_tool_registry()
        expected_names = [
            "fetch_message",
            "fetch_thread",
            "fetch_channel_history",
            "get_queued_messages",
            "get_user_channel_rules",
            "alert_now",
            "queue_for_digest",
            "link_messages",
        ]
        for name in expected_names:
            assert registry.get(name) is not None, f"Missing tool: {name}"

    def test_registry_returns_definitions(self):
        """get_definitions() should return 8 ToolDefinitions with correct names."""
        from app.agents.triage.tools import get_triage_tool_registry

        registry = get_triage_tool_registry()
        defs = registry.get_definitions()

        assert len(defs) == 8
        names = {d.name for d in defs}
        expected = {
            "fetch_message",
            "fetch_thread",
            "fetch_channel_history",
            "get_queued_messages",
            "get_user_channel_rules",
            "alert_now",
            "queue_for_digest",
            "link_messages",
        }
        assert names == expected


# ---------------------------------------------------------------------------
# TestSetupNode
# ---------------------------------------------------------------------------


class TestSetupNode:
    """Verify the setup node creates the correct initial state."""

    @pytest.mark.asyncio
    async def test_setup_creates_system_and_user_messages(self):
        """setup_node should produce system + user messages and zero counters."""
        from app.agents.triage.nodes import setup_node

        state = {
            "user_id": "u1",
            "channel_id": "C111",
            "message_ts": "1234.5678",
            "sender_slack_id": "U999",
            "event_type": "message",
            "thread_ts": None,
            "bot_id": None,
            "message_text_fallback": "",
            "sensitivity": "normal",
            "custom_rules": None,
            "p0_definition": None,
            "p1_definition": None,
            "p2_definition": None,
            "p3_definition": None,
            "p1_max_wait_minutes": 30,
            "p1_settled_threshold_minutes": 5,
            "eod_review_time": "17:00",
            "llm_messages": [],
            "tool_calls": None,
            "tool_iteration": 0,
            "tool_call_count": 0,
            "action_taken": None,
            "classification_id": None,
            "error": None,
            "needs_review": False,
        }

        config = {"configurable": {"db": AsyncMock(), "user_id": "u1"}}

        result = await setup_node(state, config)

        # Should have exactly 2 messages: system + user
        msgs = result["llm_messages"]
        assert len(msgs) == 2
        assert msgs[0].role == "system"
        assert msgs[1].role == "user"

        # Counters should be zero / None / False
        assert result["tool_iteration"] == 0
        assert result["tool_call_count"] == 0
        assert result["tool_calls"] is None
        assert result["action_taken"] is None
        assert result["classification_id"] is None
        assert result["error"] is None
        assert result["needs_review"] is False

    @pytest.mark.asyncio
    async def test_setup_includes_thread_ts_when_present(self):
        """User message should mention thread_ts when set."""
        from app.agents.triage.nodes import setup_node

        state = {
            "user_id": "u1",
            "channel_id": "C111",
            "message_ts": "1234.5678",
            "sender_slack_id": "U999",
            "event_type": "message",
            "thread_ts": "1111.0000",
            "bot_id": None,
            "message_text_fallback": "hello",
            "sensitivity": "normal",
            "custom_rules": None,
            "p0_definition": None,
            "p1_definition": None,
            "p2_definition": None,
            "p3_definition": None,
            "p1_max_wait_minutes": 30,
            "p1_settled_threshold_minutes": 5,
            "eod_review_time": "17:00",
            "llm_messages": [],
            "tool_calls": None,
            "tool_iteration": 0,
            "tool_call_count": 0,
            "action_taken": None,
            "classification_id": None,
            "error": None,
            "needs_review": False,
        }

        config = {"configurable": {"db": AsyncMock(), "user_id": "u1"}}

        result = await setup_node(state, config)
        user_msg = result["llm_messages"][1].content

        assert "1111.0000" in user_msg
        assert "thread_ts" in user_msg

    @pytest.mark.asyncio
    async def test_setup_includes_fallback_text(self):
        """User message should include the fallback text when provided."""
        from app.agents.triage.nodes import setup_node

        state = {
            "user_id": "u1",
            "channel_id": "C111",
            "message_ts": "1234.5678",
            "sender_slack_id": "U999",
            "event_type": "message",
            "thread_ts": None,
            "bot_id": None,
            "message_text_fallback": "urgent server down",
            "sensitivity": "normal",
            "custom_rules": None,
            "p0_definition": None,
            "p1_definition": None,
            "p2_definition": None,
            "p3_definition": None,
            "p1_max_wait_minutes": 30,
            "p1_settled_threshold_minutes": 5,
            "eod_review_time": "17:00",
            "llm_messages": [],
            "tool_calls": None,
            "tool_iteration": 0,
            "tool_call_count": 0,
            "action_taken": None,
            "classification_id": None,
            "error": None,
            "needs_review": False,
        }

        config = {"configurable": {"db": AsyncMock(), "user_id": "u1"}}

        result = await setup_node(state, config)
        user_msg = result["llm_messages"][1].content

        assert "urgent server down" in user_msg


# ---------------------------------------------------------------------------
# TestRouting
# ---------------------------------------------------------------------------


class TestRouting:
    """Verify the routing functions return the correct next node."""

    def test_route_after_llm_with_tool_calls(self):
        """Should route to tool_node when tool_calls are present."""
        from app.agents.triage.nodes import route_after_llm

        state = {
            "error": None,
            "action_taken": None,
            "tool_calls": [MagicMock()],
        }
        assert route_after_llm(state) == "tool_node"

    def test_route_after_llm_with_action_taken(self):
        """Should route to end when action already taken."""
        from app.agents.triage.nodes import route_after_llm

        state = {
            "error": None,
            "action_taken": "queued",
            "tool_calls": None,
        }
        assert route_after_llm(state) == "end"

    def test_route_after_llm_with_error(self):
        """Should route to end on error."""
        from app.agents.triage.nodes import route_after_llm

        state = {
            "error": "LLM call failed: timeout",
            "action_taken": None,
            "tool_calls": None,
        }
        assert route_after_llm(state) == "end"

    def test_route_after_llm_no_tools_no_action(self):
        """Should route to end as fallback when no tool_calls and no action."""
        from app.agents.triage.nodes import route_after_llm

        state = {
            "error": None,
            "action_taken": None,
            "tool_calls": None,
        }
        assert route_after_llm(state) == "end"

    def test_route_after_llm_error_takes_precedence(self):
        """Error should take precedence over tool_calls."""
        from app.agents.triage.nodes import route_after_llm

        state = {
            "error": "something broke",
            "action_taken": None,
            "tool_calls": [MagicMock()],
        }
        assert route_after_llm(state) == "end"

    def test_route_after_tool_continues(self):
        """Should route back to llm_node when no action taken."""
        from app.agents.triage.nodes import route_after_tool

        state = {
            "action_taken": None,
            "needs_review": False,
        }
        assert route_after_tool(state) == "llm_node"

    def test_route_after_tool_with_action(self):
        """Should route to end when action taken."""
        from app.agents.triage.nodes import route_after_tool

        state = {
            "action_taken": "alerted",
            "needs_review": False,
        }
        assert route_after_tool(state) == "end"

    def test_route_after_tool_with_needs_review(self):
        """Should route to end when needs_review is True."""
        from app.agents.triage.nodes import route_after_tool

        state = {
            "action_taken": None,
            "needs_review": True,
        }
        assert route_after_tool(state) == "end"
