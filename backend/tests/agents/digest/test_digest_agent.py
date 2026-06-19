"""Integration tests for the digest agent: compose_and_deliver, routing, setup, and registry."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.llm import LLMMessage


# ---------------------------------------------------------------------------
# TestDigestAgentComposeAndDeliver
# ---------------------------------------------------------------------------


class TestDigestAgentComposeAndDeliver:
    """Verify DigestAgent.compose_and_deliver returns the expected result structure."""

    @pytest.mark.asyncio
    async def test_returns_result_structure(self):
        """compose_and_deliver() should return dict with all expected keys on success."""
        from app.agents.digest.agent import DigestAgent

        db = AsyncMock()
        agent = DigestAgent(db)

        # Replace the compiled graph with a mock that returns a "successful" state
        mock_graph = AsyncMock()
        mock_graph.ainvoke.return_value = {
            "digest_sent": True,
            "digest_record_id": "rec-456",
            "error": None,
        }
        agent.graph = mock_graph

        result = await agent.compose_and_deliver(
            user_id="u1",
            digest_type="eod",
            groups=[{"group_id": "g1", "messages": [{"abstract": "test"}]}],
            p3_count=3,
        )

        expected_keys = {"digest_sent", "digest_record_id", "error"}
        assert set(result.keys()) == expected_keys
        assert result["digest_sent"] is True
        assert result["digest_record_id"] == "rec-456"
        assert result["error"] is None

    @pytest.mark.asyncio
    async def test_handles_error_gracefully(self):
        """compose_and_deliver() should return error dict on graph failure, not raise."""
        from app.agents.digest.agent import DigestAgent

        db = AsyncMock()
        agent = DigestAgent(db)

        mock_graph = AsyncMock()
        mock_graph.ainvoke.side_effect = RuntimeError("LLM boom")
        agent.graph = mock_graph

        result = await agent.compose_and_deliver(
            user_id="u1",
            digest_type="p1",
            groups=[{"group_id": "g1", "messages": []}],
        )

        assert result["digest_sent"] is False
        assert result["digest_record_id"] is None
        assert "LLM boom" in result["error"]


# ---------------------------------------------------------------------------
# TestDigestToolRegistry
# ---------------------------------------------------------------------------


class TestDigestToolRegistry:
    """Verify the digest tool registry has all 5 tools."""

    def test_registry_has_all_tools(self):
        """All 5 digest tools should be registered."""
        from app.agents.digest.tools import get_digest_tool_registry

        registry = get_digest_tool_registry()
        expected_names = [
            "digest_fetch_thread",
            "digest_fetch_channel_history",
            "send_digest_dm",
            "save_digest_record",
            "mark_delivered",
        ]
        for name in expected_names:
            assert registry.get(name) is not None, f"Missing tool: {name}"

    def test_registry_returns_definitions(self):
        """get_definitions() should return 5 ToolDefinitions with correct names."""
        from app.agents.digest.tools import get_digest_tool_registry

        registry = get_digest_tool_registry()
        defs = registry.get_definitions()

        assert len(defs) == 5
        names = {d.name for d in defs}
        expected = {
            "digest_fetch_thread",
            "digest_fetch_channel_history",
            "send_digest_dm",
            "save_digest_record",
            "mark_delivered",
        }
        assert names == expected


# ---------------------------------------------------------------------------
# TestDigestSetupNode
# ---------------------------------------------------------------------------


class TestDigestSetupNode:
    """Verify the setup node creates the correct initial state."""

    @pytest.mark.asyncio
    async def test_setup_creates_messages_from_groups(self):
        """Setup node should create system prompt + user message listing groups."""
        from app.agents.digest.nodes import setup_node

        state = {
            "user_id": "u1",
            "digest_type": "eod",
            "groups": [
                {
                    "group_id": "g1",
                    "messages": [
                        {
                            "channel_name": "general",
                            "sender_name": "Alice",
                            "abstract": "Server down alert",
                            "permalink": "https://slack.com/msg1",
                        },
                    ],
                },
                {
                    "group_id": "g2",
                    "messages": [
                        {
                            "channel_name": "dev",
                            "sender_name": "Bob",
                            "abstract": "PR review needed",
                            "permalink": "https://slack.com/msg2",
                        },
                        {
                            "channel_name": "dev",
                            "sender_name": "Carol",
                            "abstract": "Deployment ready",
                            "permalink": "",
                        },
                    ],
                },
            ],
            "p3_count": 0,
            "llm_messages": [],
            "tool_calls": None,
            "tool_iteration": 0,
            "tool_call_count": 0,
            "digest_sent": False,
            "digest_record_id": None,
            "error": None,
        }

        config = {"configurable": {"db": AsyncMock(), "user_id": "u1"}}

        result = await setup_node(state, config)

        # Should have exactly 2 messages: system + user
        msgs = result["llm_messages"]
        assert len(msgs) == 2
        assert msgs[0].role == "system"
        assert msgs[1].role == "user"

        # User message should mention the groups and messages
        user_content = msgs[1].content
        assert "2 message group(s)" in user_content
        assert "g1" in user_content
        assert "g2" in user_content
        assert "Alice" in user_content
        assert "Server down alert" in user_content
        assert "Bob" in user_content
        assert "PR review needed" in user_content
        assert "Carol" in user_content
        assert "Deployment ready" in user_content

        # Counters should be zero / None / False
        assert result["tool_iteration"] == 0
        assert result["tool_call_count"] == 0
        assert result["tool_calls"] is None
        assert result["digest_sent"] is False
        assert result["digest_record_id"] is None
        assert result["error"] is None

    @pytest.mark.asyncio
    async def test_setup_with_empty_groups(self):
        """Setup node should handle empty groups list gracefully."""
        from app.agents.digest.nodes import setup_node

        state = {
            "user_id": "u1",
            "digest_type": "p1",
            "groups": [],
            "p3_count": 0,
            "llm_messages": [],
            "tool_calls": None,
            "tool_iteration": 0,
            "tool_call_count": 0,
            "digest_sent": False,
            "digest_record_id": None,
            "error": None,
        }

        config = {"configurable": {"db": AsyncMock(), "user_id": "u1"}}

        result = await setup_node(state, config)

        msgs = result["llm_messages"]
        assert len(msgs) == 2
        assert "0 message group(s)" in msgs[1].content

    @pytest.mark.asyncio
    async def test_setup_includes_permalink_when_present(self):
        """User message should include permalink links when provided."""
        from app.agents.digest.nodes import setup_node

        state = {
            "user_id": "u1",
            "digest_type": "eod",
            "groups": [
                {
                    "group_id": "g1",
                    "messages": [
                        {
                            "channel_name": "general",
                            "sender_name": "Alice",
                            "abstract": "Test message",
                            "permalink": "https://slack.com/msg1",
                        },
                    ],
                },
            ],
            "p3_count": 0,
            "llm_messages": [],
            "tool_calls": None,
            "tool_iteration": 0,
            "tool_call_count": 0,
            "digest_sent": False,
            "digest_record_id": None,
            "error": None,
        }

        config = {"configurable": {"db": AsyncMock(), "user_id": "u1"}}

        result = await setup_node(state, config)
        user_content = result["llm_messages"][1].content

        assert "https://slack.com/msg1" in user_content
        assert "View" in user_content


# ---------------------------------------------------------------------------
# TestDigestRouting
# ---------------------------------------------------------------------------


class TestDigestRouting:
    """Verify the routing functions return the correct next node."""

    def test_route_after_llm_with_tool_calls(self):
        """Should route to tool_node when tool_calls present."""
        from app.agents.digest.nodes import route_after_llm

        state = {
            "error": None,
            "digest_sent": False,
            "tool_calls": [MagicMock()],
        }
        assert route_after_llm(state) == "tool_node"

    def test_route_after_llm_when_digest_sent(self):
        """Should route to end when digest already sent."""
        from app.agents.digest.nodes import route_after_llm

        state = {
            "error": None,
            "digest_sent": True,
            "tool_calls": None,
        }
        assert route_after_llm(state) == "end"

    def test_route_after_llm_with_error(self):
        """Should route to end on error."""
        from app.agents.digest.nodes import route_after_llm

        state = {
            "error": "LLM call failed: timeout",
            "digest_sent": False,
            "tool_calls": None,
        }
        assert route_after_llm(state) == "end"

    def test_route_after_llm_no_tools_no_digest(self):
        """Should route to end as fallback when no tool_calls and digest not sent."""
        from app.agents.digest.nodes import route_after_llm

        state = {
            "error": None,
            "digest_sent": False,
            "tool_calls": None,
        }
        assert route_after_llm(state) == "end"

    def test_route_after_llm_error_takes_precedence(self):
        """Error should take precedence over tool_calls."""
        from app.agents.digest.nodes import route_after_llm

        state = {
            "error": "something broke",
            "digest_sent": False,
            "tool_calls": [MagicMock()],
        }
        assert route_after_llm(state) == "end"

    def test_route_after_tool_continues(self):
        """Should route to llm_node when digest not yet sent."""
        from app.agents.digest.nodes import route_after_tool

        state = {
            "digest_sent": False,
            "digest_record_id": None,
            "error": None,
            "tool_call_count": 2,
        }
        assert route_after_tool(state) == "llm_node"

    def test_route_after_tool_ends_when_done(self):
        """Should end when both digest_sent and digest_record_id are set."""
        from app.agents.digest.nodes import route_after_tool

        state = {
            "digest_sent": True,
            "digest_record_id": "rec-123",
            "error": None,
            "tool_call_count": 5,
        }
        assert route_after_tool(state) == "end"

    def test_route_after_tool_ends_on_error(self):
        """Should end when error is set."""
        from app.agents.digest.nodes import route_after_tool

        state = {
            "digest_sent": False,
            "digest_record_id": None,
            "error": "tool failed",
            "tool_call_count": 1,
        }
        assert route_after_tool(state) == "end"

    def test_route_after_tool_ends_at_max_calls(self):
        """Should end when tool_call_count reaches MAX_TOOL_CALLS."""
        from app.agents.digest.nodes import route_after_tool
        from app.agents.digest.prompt import MAX_TOOL_CALLS

        state = {
            "digest_sent": False,
            "digest_record_id": None,
            "error": None,
            "tool_call_count": MAX_TOOL_CALLS,
        }
        assert route_after_tool(state) == "end"

    def test_route_after_tool_continues_without_record_id(self):
        """Should continue when digest_sent but no record_id yet."""
        from app.agents.digest.nodes import route_after_tool

        state = {
            "digest_sent": True,
            "digest_record_id": None,
            "error": None,
            "tool_call_count": 3,
        }
        assert route_after_tool(state) == "llm_node"
