import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from collections.abc import AsyncIterator

from app.agents import AlfredAgent
from app.agents.nodes import (
    build_prompt_messages,
    generate_response_stream_with_tools,
    generate_response_with_tools,
    process_message,
    retrieve_context,
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
        state: AgentState = {
            "session_id": "test-session",
            "user_id": "test-user",
            "user_message": "Hello!",
            "is_remember_command": False,
            "remember_content": None,
            "context_messages": [],
            "memories": [],
            "response": "",
            "response_chunks": [],
            "user_message_id": "",
            "assistant_message_id": "",
            "error": None,
        }

        result = await process_message(state)

        assert result["error"] is None
        assert result["user_message"] == "Hello!"
        assert result["user_message_id"] != ""
        assert result["assistant_message_id"] != ""
        assert result["is_remember_command"] is False

    async def test_process_message_empty(self):
        """Should return error for empty message."""
        state: AgentState = {
            "session_id": "test-session",
            "user_id": "test-user",
            "user_message": "   ",
            "is_remember_command": False,
            "remember_content": None,
            "context_messages": [],
            "memories": [],
            "response": "",
            "response_chunks": [],
            "user_message_id": "",
            "assistant_message_id": "",
            "error": None,
        }

        result = await process_message(state)

        assert result["error"] == "Empty message"


class TestBuildPromptMessages:
    """Tests for build_prompt_messages function."""

    def test_build_prompt_basic(self):
        """Should build basic prompt with system message."""
        state: AgentState = {
            "session_id": "test",
            "user_id": "test",
            "user_message": "Hello!",
            "is_remember_command": False,
            "remember_content": None,
            "context_messages": [],
            "memories": [],
            "response": "",
            "response_chunks": [],
            "user_message_id": "",
            "assistant_message_id": "",
            "error": None,
        }

        messages = build_prompt_messages(state)

        assert len(messages) == 2
        assert messages[0].role == "system"
        assert messages[1].role == "user"
        assert messages[1].content == "Hello!"

    def test_build_prompt_with_history(self):
        """Should include conversation history."""
        state: AgentState = {
            "session_id": "test",
            "user_id": "test",
            "user_message": "Thanks!",
            "is_remember_command": False,
            "remember_content": None,
            "context_messages": [
                {"role": "user", "content": "Hi"},
                {"role": "assistant", "content": "Hello!"},
            ],
            "memories": [],
            "response": "",
            "response_chunks": [],
            "user_message_id": "",
            "assistant_message_id": "",
            "error": None,
        }

        messages = build_prompt_messages(state)

        assert len(messages) == 4
        assert messages[0].role == "system"
        assert messages[1].role == "user"
        assert messages[1].content == "Hi"
        assert messages[2].role == "assistant"
        assert messages[2].content == "Hello!"
        assert messages[3].role == "user"
        assert messages[3].content == "Thanks!"

    def test_build_prompt_with_memories(self):
        """Should include memories in system prompt."""
        state: AgentState = {
            "session_id": "test",
            "user_id": "test",
            "user_message": "Hello!",
            "is_remember_command": False,
            "remember_content": None,
            "context_messages": [],
            "memories": ["User prefers Python", "User is a developer"],
            "response": "",
            "response_chunks": [],
            "user_message_id": "",
            "assistant_message_id": "",
            "error": None,
        }

        messages = build_prompt_messages(state)

        assert len(messages) == 2
        assert "User prefers Python" in messages[0].content
        assert "User is a developer" in messages[0].content


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

    async def test_agent_run(self, mock_db, mock_provider):
        """Should run agent and return response."""
        # Mock the message and memory repositories
        with patch("app.agents.alfred.MessageRepository") as MockMsgRepo, \
             patch("app.agents.alfred.MemoryRepository") as MockMemRepo:
            mock_msg_repo = AsyncMock()
            mock_msg_repo.get_recent_messages.return_value = []
            mock_msg_repo.create_message.return_value = MagicMock(id="msg-id")
            MockMsgRepo.return_value = mock_msg_repo

            mock_mem_repo = AsyncMock()
            mock_mem_repo.search_similar.return_value = []
            MockMemRepo.return_value = mock_mem_repo

            agent = AlfredAgent(db=mock_db, llm_provider=mock_provider)
            response = await agent.run(
                session_id="test-session",
                user_id="test-user",
                message="Hello!",
            )

            assert response == "Hello! How can I help you?"
            assert mock_msg_repo.create_message.call_count == 2

    async def test_agent_stream(self, mock_db, mock_provider):
        """Should stream response events."""
        with patch("app.agents.alfred.MessageRepository") as MockMsgRepo, \
             patch("app.agents.alfred.MemoryRepository") as MockMemRepo:
            mock_msg_repo = AsyncMock()
            mock_msg_repo.get_recent_messages.return_value = []
            mock_msg_repo.create_message.return_value = MagicMock(id="msg-id")
            MockMsgRepo.return_value = mock_msg_repo

            mock_mem_repo = AsyncMock()
            mock_mem_repo.search_similar.return_value = []
            MockMemRepo.return_value = mock_mem_repo

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
        with patch("app.agents.alfred.MessageRepository"), \
             patch("app.agents.alfred.MemoryRepository"):
            agent = AlfredAgent(db=mock_db, llm_provider=mock_provider)

            with pytest.raises(ValueError, match="Empty message"):
                await agent.run(
                    session_id="test-session",
                    user_id="test-user",
                    message="   ",
                )


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
        "is_remember_command": False,
        "remember_content": None,
        "context_messages": [],
        "memories": [],
        "response": "",
        "response_chunks": [],
        "user_message_id": "msg-1",
        "assistant_message_id": "msg-2",
        "error": None,
    }
    state.update(overrides)  # type: ignore[typeddict-item]
    return state


class TestReActLoop:
    """Tests for the ReAct loop (generate_response_with_tools)."""

    async def test_no_tool_call(self):
        """When LLM returns text directly, should return it without calling tools."""
        provider = MockLLMProvider("Direct answer")
        registry = ToolRegistry()
        registry.register(MockTool())

        state = _make_state()
        result = await generate_response_with_tools(state, provider, registry)

        assert result["response"] == "Direct answer"

    async def test_tool_call_then_text(self):
        """LLM calls a tool, gets result, then returns final text."""
        provider = MockLLMProvider()
        provider._tool_responses = [
            # First call: LLM requests tool
            LLMResponse(
                tool_calls=[ToolCall(id="call_1", name="mock_tool", arguments={"input": "test"})]
            ),
            # Second call: LLM returns final text
            LLMResponse(content="Here is the answer based on the tool result."),
        ]

        mock_tool = MockTool(result="Tool output data")
        registry = ToolRegistry()
        registry.register(mock_tool)

        state = _make_state()
        result = await generate_response_with_tools(state, provider, registry)

        assert result["response"] == "Here is the answer based on the tool result."
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

        # Need at least one tool registered so tool_defs is non-empty
        registry = ToolRegistry()
        registry.register(MockTool())

        state = _make_state()
        result = await generate_response_with_tools(state, provider, registry)

        assert result["response"] == "Fallback response"

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

        state = _make_state()
        result = await generate_response_with_tools(state, provider, registry)

        # Last iteration uses plain generate() without tools, so only 2 tool executions
        # (MAX_TOOL_ITERATIONS=3, iterations 1-2 allow tools, iteration 3 forces text)
        assert mock_tool.call_count == 2
        # Final response comes from plain generate() fallback
        assert result["response"] == "Forced text response"

    async def test_error_state_skips(self):
        """Should return empty dict if state has an error."""
        provider = MockLLMProvider()
        registry = ToolRegistry()

        state = _make_state(error="Previous error")
        result = await generate_response_with_tools(state, provider, registry)

        assert result == {}


class TestReActStreamLoop:
    """Tests for the streaming ReAct loop."""

    async def test_stream_no_tool_call(self):
        """When LLM streams text directly, should yield token events."""
        provider = MockLLMProvider("Streamed answer here")
        registry = ToolRegistry()

        state = _make_state()
        events = []
        async for event in generate_response_stream_with_tools(state, provider, registry):
            events.append(event)

        token_events = [e for e in events if e["type"] == "token"]
        assert len(token_events) > 0
        full_text = "".join(e["content"] for e in token_events)
        assert "Streamed" in full_text

    async def test_stream_tool_call_then_text(self):
        """Should emit tool_use event, then stream final text."""
        provider = MockLLMProvider()
        provider._tool_responses = [
            # First call: tool call
            LLMResponse(
                tool_calls=[ToolCall(id="call_1", name="mock_tool", arguments={"input": "test"})]
            ),
            # Second call: text response
            LLMResponse(content="Final streamed answer"),
        ]

        mock_tool = MockTool(result="tool data")
        registry = ToolRegistry()
        registry.register(mock_tool)

        state = _make_state()
        events = []
        async for event in generate_response_stream_with_tools(state, provider, registry):
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
        """Should yield nothing if state has an error."""
        provider = MockLLMProvider()
        registry = ToolRegistry()

        state = _make_state(error="Previous error")
        events = []
        async for event in generate_response_stream_with_tools(state, provider, registry):
            events.append(event)

        assert len(events) == 0


class TestAgentWithTools:
    """Tests for AlfredAgent with tool registry."""

    @pytest.fixture
    def mock_db(self):
        return AsyncMock()

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

        with patch("app.agents.alfred.MessageRepository") as MockMsgRepo, \
             patch("app.agents.alfred.MemoryRepository") as MockMemRepo:
            mock_msg_repo = AsyncMock()
            mock_msg_repo.get_recent_messages.return_value = []
            mock_msg_repo.create_message.return_value = MagicMock(id="msg-id")
            MockMsgRepo.return_value = mock_msg_repo

            mock_mem_repo = AsyncMock()
            mock_mem_repo.search_similar.return_value = []
            MockMemRepo.return_value = mock_mem_repo

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

        with patch("app.agents.alfred.MessageRepository") as MockMsgRepo, \
             patch("app.agents.alfred.MemoryRepository") as MockMemRepo:
            mock_msg_repo = AsyncMock()
            mock_msg_repo.get_recent_messages.return_value = []
            mock_msg_repo.create_message.return_value = MagicMock(id="msg-id")
            MockMsgRepo.return_value = mock_msg_repo

            mock_mem_repo = AsyncMock()
            mock_mem_repo.search_similar.return_value = []
            MockMemRepo.return_value = mock_mem_repo

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
