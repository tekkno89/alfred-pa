import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from collections.abc import AsyncIterator
from zoneinfo import ZoneInfo

from app.agents import AlfredAgent
from app.agents.nodes import (
    build_prompt_messages,
    process_message,
)
from app.agents.state import AgentState
from app.core.llm import LLMMessage, LLMProvider, LLMResponse, ToolCall, ToolDefinition
from app.tools.base import BaseTool
from app.tools.registry import ToolRegistry


class MockLLMProvider(LLMProvider):
    """Mock LLM provider for testing."""

    def __init__(self, response: str = "Mock response"):
        self.response = response
        self._tool_call_count = 0
        self._tool_responses: list[LLMResponse] = []

    async def generate(
        self,
        messages: list[LLMMessage],
        *,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> str:
        return self.response

    async def stream(
        self,
        messages: list[LLMMessage],
        *,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> AsyncIterator[str]:
        for word in self.response.split():
            yield word + " "

    async def generate_with_tools(
        self,
        messages: list[LLMMessage],
        tools: list[ToolDefinition],
        *,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> LLMResponse:
        if self._tool_responses:
            resp = self._tool_responses[self._tool_call_count]
            self._tool_call_count += 1
            return resp
        return LLMResponse(content=self.response)

    async def stream_with_tools(
        self,
        messages: list[LLMMessage],
        tools: list[ToolDefinition],
        *,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> AsyncIterator[LLMResponse]:
        if self._tool_responses:
            resp = self._tool_responses[self._tool_call_count]
            self._tool_call_count += 1
            if resp.tool_calls:
                yield resp
            elif resp.content:
                for word in resp.content.split():
                    yield LLMResponse(content=word + " ")
        else:
            for word in self.response.split():
                yield LLMResponse(content=word + " ")


class TestProcessMessage:
    """Tests for process_message node."""

    async def test_process_message_success(self):
        """Should process valid message."""
        state = _make_state(user_message="Hello!")

        result = await process_message(state)

        assert result["error"] is None
        assert result["user_message"] == "Hello!"
        assert result["user_message_id"] != ""
        assert result["assistant_message_id"] != ""

    async def test_process_message_empty(self):
        """Should return error for empty message."""
        state = _make_state(user_message="   ")

        result = await process_message(state)

        assert result["error"] == "Empty message"


class TestBuildPromptMessages:
    """Tests for build_prompt_messages function."""

    def test_build_prompt_basic(self):
        """Should build basic prompt with system message."""
        state = _make_state(user_message="Hello!")

        messages = build_prompt_messages(state)

        assert len(messages) == 2
        assert messages[0].role == "system"
        assert messages[1].role == "user"
        assert messages[1].content == "Hello!"

    def test_build_prompt_with_history(self):
        """Should include conversation history."""
        state = _make_state(
            user_message="Thanks!",
            context_messages=[
                {"role": "user", "content": "Hi"},
                {"role": "assistant", "content": "Hello!"},
            ],
        )

        messages = build_prompt_messages(state)

        assert len(messages) == 4
        assert messages[0].role == "system"
        assert messages[1].role == "user"
        assert messages[1].content == "Hi"
        assert messages[2].role == "assistant"
        assert messages[2].content == "Hello!"
        assert messages[3].role == "user"
        assert messages[3].content == "Thanks!"

    def test_build_prompt_with_summary(self):
        """Should include conversation summary in system prompt."""
        state = _make_state(
            user_message="Hello!",
            conversation_summary="Earlier, the user discussed Python and databases.",
        )

        messages = build_prompt_messages(state)

        assert len(messages) == 2
        assert "Summary of earlier conversation" in messages[0].content
        assert "Python and databases" in messages[0].content

    def test_build_prompt_with_timezone(self):
        """Should use user's local timezone for date/time in system prompt."""
        state = _make_state(user_message="Hello!")

        # Fix time to 11 PM PST on March 4 (which is March 5 in UTC)
        fake_utc = datetime(2026, 3, 5, 7, 0, 0, tzinfo=timezone.utc)

        with patch("app.agents.nodes.datetime") as mock_dt:
            mock_dt.now.return_value = fake_utc.astimezone(ZoneInfo("America/Los_Angeles"))
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)

            messages = build_prompt_messages(state, tz="America/Los_Angeles")

        system = messages[0].content
        # Should show March 4 (PST local date), not March 5 (UTC)
        assert "March 04, 2026" in system
        assert "11:00 PM" in system

    def test_build_prompt_without_timezone_uses_utc(self):
        """Without timezone, should fall back to UTC."""
        state = _make_state(user_message="Hello!")

        messages = build_prompt_messages(state)

        system = messages[0].content
        assert "Today's date is" in system
        assert "The current time is" in system


class TestAlfredAgent:
    """Tests for AlfredAgent class."""

    @pytest.fixture
    def mock_db(self):
        """Create mock database session."""
        return AsyncMock()

    @pytest.fixture
    def mock_provider(self):
        """Create mock LLM provider."""
        return MockLLMProvider("Hello! How can I help you?")

    def _patch_repos(self):
        """Return a context manager that patches MessageRepository and SessionRepository."""
        mock_msg_repo = AsyncMock()
        mock_msg_repo.get_session_messages.return_value = []
        mock_msg_repo.get_messages_after.return_value = []
        mock_msg_repo.create_message.return_value = MagicMock(id="msg-id")

        mock_session_repo = AsyncMock()
        mock_session = MagicMock()
        mock_session.conversation_summary = None
        mock_session.summary_through_id = None
        mock_session_repo.get.return_value = mock_session

        class PatchContext:
            def __init__(self):
                self.msg_repo = mock_msg_repo
                self.session_repo = mock_session_repo
                self._patches = []

            def __enter__(self):
                p1 = patch("app.agents.nodes.MessageRepository", return_value=self.msg_repo)
                p2 = patch("app.agents.nodes.SessionRepository", return_value=self.session_repo)
                self._patches = [p1, p2]
                p1.start()
                p2.start()
                return self

            def __exit__(self, *args):
                for p in self._patches:
                    p.stop()

        return PatchContext()

    async def test_agent_run(self, mock_db, mock_provider):
        """Should run agent and return response."""
        with self._patch_repos() as ctx:
            agent = AlfredAgent(db=mock_db, llm_provider=mock_provider)
            response = await agent.run(
                session_id="test-session",
                user_id="test-user",
                message="Hello!",
            )

            assert response == "Hello! How can I help you?"
            assert ctx.msg_repo.create_message.call_count == 2

    async def test_agent_stream(self, mock_db, mock_provider):
        """Should stream response events."""
        with self._patch_repos():
            agent = AlfredAgent(db=mock_db, llm_provider=mock_provider)

            events = []
            async for event in agent.stream(
                session_id="test-session",
                user_id="test-user",
                message="Hello!",
            ):
                events.append(event)

            assert len(events) > 0
            # All events should be dicts with a "type" key
            assert all(isinstance(e, dict) and "type" in e for e in events)
            token_events = [e for e in events if e["type"] == "token"]
            full_response = "".join(e["content"] for e in token_events)
            assert "Hello!" in full_response

    async def test_agent_empty_message(self, mock_db, mock_provider):
        """Should raise error for empty message."""
        agent = AlfredAgent(db=mock_db, llm_provider=mock_provider)

        with pytest.raises(ValueError, match="Empty message"):
            await agent.run(
                session_id="test-session",
                user_id="test-user",
                message="   ",
            )

    async def test_agent_stream_empty_message(self, mock_db, mock_provider):
        """Should raise error for empty message in stream mode."""
        agent = AlfredAgent(db=mock_db, llm_provider=mock_provider)

        with pytest.raises(ValueError, match="Empty message"):
            async for _ in agent.stream(
                session_id="test-session",
                user_id="test-user",
                message="   ",
            ):
                pass

    async def test_agent_captures_context_usage(self, mock_db, mock_provider):
        """Should capture context_usage in non-streaming mode."""
        with self._patch_repos():
            agent = AlfredAgent(db=mock_db, llm_provider=mock_provider)
            await agent.run(
                session_id="test-session",
                user_id="test-user",
                message="Hello!",
            )

            assert agent.last_context_usage is not None
            assert "tokens_used" in agent.last_context_usage
            assert "token_limit" in agent.last_context_usage
            assert "percentage" in agent.last_context_usage

    async def test_agent_stream_emits_context_usage(self, mock_db, mock_provider):
        """Should emit context_usage event in streaming mode."""
        with self._patch_repos():
            agent = AlfredAgent(db=mock_db, llm_provider=mock_provider)

            events = []
            async for event in agent.stream(
                session_id="test-session",
                user_id="test-user",
                message="Hello!",
            ):
                events.append(event)

            context_events = [e for e in events if e.get("type") == "context_usage"]
            assert len(context_events) == 1
            assert "tokens_used" in context_events[0]
            assert "token_limit" in context_events[0]


class MockTool(BaseTool):
    """Mock tool for testing."""

    name = "mock_tool"
    description = "A mock tool for testing"
    parameters_schema = {
        "type": "object",
        "properties": {
            "input": {"type": "string", "description": "Input value"},
        },
        "required": ["input"],
    }

    def __init__(self, result: str = "Mock tool result"):
        self.result = result
        self.call_count = 0

    async def execute(self, **kwargs) -> str:
        self.call_count += 1
        return self.result


def _make_state(**overrides) -> AgentState:
    """Helper to create a test AgentState."""
    state: AgentState = {
        "session_id": "test-session",
        "user_id": "test-user",
        "user_message": "Test message",
        "context_messages": [],
        "conversation_summary": None,
        "context_usage": None,
        "response": "",
        "llm_messages": [],
        "tool_calls": None,
        "tool_iteration": 0,
        "tool_results_metadata": None,
        "todo_context": None,
        "user_message_id": "msg-1",
        "assistant_message_id": "msg-2",
        "error": None,
    }
    state.update(overrides)  # type: ignore[typeddict-item]
    return state


class TestReActLoop:
    """Tests for the ReAct loop via the graph."""

    def _patch_repos(self):
        """Return a context manager that patches repos for ReAct tests."""
        mock_msg_repo = AsyncMock()
        mock_msg_repo.get_session_messages.return_value = []
        mock_msg_repo.get_messages_after.return_value = []
        mock_msg_repo.create_message.return_value = MagicMock(id="msg-id")

        mock_session_repo = AsyncMock()
        mock_session = MagicMock()
        mock_session.conversation_summary = None
        mock_session.summary_through_id = None
        mock_session_repo.get.return_value = mock_session

        class PatchContext:
            def __init__(self):
                self.msg_repo = mock_msg_repo
                self.session_repo = mock_session_repo
                self._patches = []

            def __enter__(self):
                p1 = patch("app.agents.nodes.MessageRepository", return_value=self.msg_repo)
                p2 = patch("app.agents.nodes.SessionRepository", return_value=self.session_repo)
                self._patches = [p1, p2]
                p1.start()
                p2.start()
                return self

            def __exit__(self, *args):
                for p in self._patches:
                    p.stop()

        return PatchContext()

    async def test_no_tool_call(self):
        """When LLM returns text directly, should return it without calling tools."""
        provider = MockLLMProvider("Direct answer")
        registry = ToolRegistry()
        registry.register(MockTool())

        mock_db = AsyncMock()
        with self._patch_repos():
            agent = AlfredAgent(db=mock_db, llm_provider=provider, tool_registry=registry)
            response = await agent.run(
                session_id="test-session",
                user_id="test-user",
                message="Hello",
            )

            assert response == "Direct answer"

    async def test_tool_call_then_text(self):
        """LLM calls a tool, gets result, then returns final text."""
        provider = MockLLMProvider()
        provider._tool_responses = [
            LLMResponse(
                tool_calls=[ToolCall(id="call_1", name="mock_tool", arguments={"input": "test"})]
            ),
            LLMResponse(content="Here is the answer based on the tool result."),
        ]

        mock_tool = MockTool(result="Tool output data")
        registry = ToolRegistry()
        registry.register(mock_tool)

        mock_db = AsyncMock()
        with self._patch_repos():
            agent = AlfredAgent(db=mock_db, llm_provider=provider, tool_registry=registry)
            response = await agent.run(
                session_id="test-session",
                user_id="test-user",
                message="Search for something",
            )

            assert response == "Here is the answer based on the tool result."
            assert mock_tool.call_count == 1

    async def test_unknown_tool(self):
        """Should handle unknown tool names gracefully."""
        provider = MockLLMProvider()
        provider._tool_responses = [
            LLMResponse(
                tool_calls=[ToolCall(id="call_1", name="nonexistent_tool", arguments={})]
            ),
            LLMResponse(content="Fallback response"),
        ]

        registry = ToolRegistry()
        registry.register(MockTool())

        mock_db = AsyncMock()
        with self._patch_repos():
            agent = AlfredAgent(db=mock_db, llm_provider=provider, tool_registry=registry)
            response = await agent.run(
                session_id="test-session",
                user_id="test-user",
                message="Search for something",
            )

            assert response == "Fallback response"

    async def test_max_iterations(self):
        """Should stop after max iterations by falling back to plain generate."""
        provider = MockLLMProvider(response="Forced text response")
        # Always request tool calls — should hit the limit
        provider._tool_responses = [
            LLMResponse(
                tool_calls=[ToolCall(id=f"call_{i}", name="mock_tool", arguments={"input": "x"})]
            )
            for i in range(10)
        ]

        mock_tool = MockTool()
        registry = ToolRegistry()
        registry.register(mock_tool)

        mock_db = AsyncMock()
        with self._patch_repos():
            agent = AlfredAgent(db=mock_db, llm_provider=provider, tool_registry=registry)
            response = await agent.run(
                session_id="test-session",
                user_id="test-user",
                message="Search for something",
            )

            # Last iteration uses plain generate() without tools, so only 2 tool executions
            # (MAX_TOOL_ITERATIONS=3, iterations 0-1 allow tools, iteration 2 forces text)
            assert mock_tool.call_count == 2
            # Final response comes from plain generate() fallback
            assert response == "Forced text response"

    async def test_error_state_skips(self):
        """Should raise ValueError when state has an error."""
        provider = MockLLMProvider()
        registry = ToolRegistry()

        mock_db = AsyncMock()
        agent = AlfredAgent(db=mock_db, llm_provider=provider, tool_registry=registry)

        with pytest.raises(ValueError, match="Empty message"):
            await agent.run(
                session_id="test-session",
                user_id="test-user",
                message="   ",
            )


class TestReActStreamLoop:
    """Tests for the streaming ReAct loop via the graph."""

    def _patch_repos(self):
        """Return a context manager that patches repos for streaming tests."""
        mock_msg_repo = AsyncMock()
        mock_msg_repo.get_session_messages.return_value = []
        mock_msg_repo.get_messages_after.return_value = []
        mock_msg_repo.create_message.return_value = MagicMock(id="msg-id")

        mock_session_repo = AsyncMock()
        mock_session = MagicMock()
        mock_session.conversation_summary = None
        mock_session.summary_through_id = None
        mock_session_repo.get.return_value = mock_session

        class PatchContext:
            def __init__(self):
                self.msg_repo = mock_msg_repo
                self.session_repo = mock_session_repo
                self._patches = []

            def __enter__(self):
                p1 = patch("app.agents.nodes.MessageRepository", return_value=self.msg_repo)
                p2 = patch("app.agents.nodes.SessionRepository", return_value=self.session_repo)
                self._patches = [p1, p2]
                p1.start()
                p2.start()
                return self

            def __exit__(self, *args):
                for p in self._patches:
                    p.stop()

        return PatchContext()

    async def test_stream_no_tool_call(self):
        """When LLM streams text directly, should yield token events."""
        provider = MockLLMProvider("Streamed answer here")
        registry = ToolRegistry()

        mock_db = AsyncMock()
        with self._patch_repos():
            agent = AlfredAgent(db=mock_db, llm_provider=provider, tool_registry=registry)
            events = []
            async for event in agent.stream(
                session_id="test-session",
                user_id="test-user",
                message="Hello",
            ):
                events.append(event)

            token_events = [e for e in events if e["type"] == "token"]
            assert len(token_events) > 0
            full_text = "".join(e["content"] for e in token_events)
            assert "Streamed" in full_text

    async def test_stream_tool_call_then_text(self):
        """Should emit tool_use event, then stream final text."""
        provider = MockLLMProvider()
        provider._tool_responses = [
            LLMResponse(
                tool_calls=[ToolCall(id="call_1", name="mock_tool", arguments={"input": "test"})]
            ),
            LLMResponse(content="Final streamed answer"),
        ]

        mock_tool = MockTool(result="tool data")
        registry = ToolRegistry()
        registry.register(mock_tool)

        mock_db = AsyncMock()
        with self._patch_repos():
            agent = AlfredAgent(db=mock_db, llm_provider=provider, tool_registry=registry)
            events = []
            async for event in agent.stream(
                session_id="test-session",
                user_id="test-user",
                message="Search for something",
            ):
                events.append(event)

            # Should have a tool_use event
            tool_events = [e for e in events if e["type"] == "tool_use"]
            assert len(tool_events) == 1
            assert tool_events[0]["tool_name"] == "mock_tool"

            # Should have token events for the final answer
            token_events = [e for e in events if e["type"] == "token"]
            full_text = "".join(e["content"] for e in token_events)
            assert "Final" in full_text

    async def test_stream_error_state_skips(self):
        """Should raise ValueError for empty message in stream mode."""
        provider = MockLLMProvider()
        registry = ToolRegistry()

        mock_db = AsyncMock()
        agent = AlfredAgent(db=mock_db, llm_provider=provider, tool_registry=registry)

        with pytest.raises(ValueError, match="Empty message"):
            async for _ in agent.stream(
                session_id="test-session",
                user_id="test-user",
                message="   ",
            ):
                pass


class TestAgentWithTools:
    """Tests for AlfredAgent with tool registry."""

    @pytest.fixture
    def mock_db(self):
        return AsyncMock()

    def _patch_repos(self):
        """Return a context manager that patches repos."""
        mock_msg_repo = AsyncMock()
        mock_msg_repo.get_session_messages.return_value = []
        mock_msg_repo.get_messages_after.return_value = []
        mock_msg_repo.create_message.return_value = MagicMock(id="msg-id")

        mock_session_repo = AsyncMock()
        mock_session = MagicMock()
        mock_session.conversation_summary = None
        mock_session.summary_through_id = None
        mock_session_repo.get.return_value = mock_session

        class PatchContext:
            def __init__(self):
                self.msg_repo = mock_msg_repo
                self.session_repo = mock_session_repo
                self._patches = []

            def __enter__(self):
                p1 = patch("app.agents.nodes.MessageRepository", return_value=self.msg_repo)
                p2 = patch("app.agents.nodes.SessionRepository", return_value=self.session_repo)
                self._patches = [p1, p2]
                p1.start()
                p2.start()
                return self

            def __exit__(self, *args):
                for p in self._patches:
                    p.stop()

        return PatchContext()

    async def test_agent_run_with_tools(self, mock_db):
        """Should use tool-calling path when registry has tools."""
        provider = MockLLMProvider()
        provider._tool_responses = [
            LLMResponse(
                tool_calls=[ToolCall(id="call_1", name="mock_tool", arguments={"input": "q"})]
            ),
            LLMResponse(content="Answer with tool data"),
        ]

        mock_tool = MockTool(result="tool result")
        registry = ToolRegistry()
        registry.register(mock_tool)

        with self._patch_repos():
            agent = AlfredAgent(
                db=mock_db,
                llm_provider=provider,
                tool_registry=registry,
            )
            response = await agent.run(
                session_id="test-session",
                user_id="test-user",
                message="Search for something",
            )

            assert response == "Answer with tool data"
            assert mock_tool.call_count == 1

    async def test_agent_stream_with_tools(self, mock_db):
        """Should stream tool_use and token events when tools are available."""
        provider = MockLLMProvider()
        provider._tool_responses = [
            LLMResponse(
                tool_calls=[ToolCall(id="call_1", name="mock_tool", arguments={"input": "q"})]
            ),
            LLMResponse(content="Streamed tool answer"),
        ]

        mock_tool = MockTool(result="tool result")
        registry = ToolRegistry()
        registry.register(mock_tool)

        with self._patch_repos():
            agent = AlfredAgent(
                db=mock_db,
                llm_provider=provider,
                tool_registry=registry,
            )

            events = []
            async for event in agent.stream(
                session_id="test-session",
                user_id="test-user",
                message="Search for something",
            ):
                events.append(event)

            tool_events = [e for e in events if e["type"] == "tool_use"]
            assert len(tool_events) >= 1

            token_events = [e for e in events if e["type"] == "token"]
            full_text = "".join(e["content"] for e in token_events)
            assert "Streamed" in full_text
