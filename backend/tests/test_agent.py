import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from collections.abc import AsyncIterator

from app.agents import AlfredAgent
from app.agents.nodes import (
    build_prompt_messages,
    process_message,
    retrieve_context,
)
from app.agents.state import AgentState
from app.core.llm import LLMMessage, LLMProvider


class MockLLMProvider(LLMProvider):
    """Mock LLM provider for testing."""

    def __init__(self, response: str = "Mock response"):
        self.response = response

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


class TestProcessMessage:
    """Tests for process_message node."""

    async def test_process_message_success(self):
        """Should process valid message."""
        state: AgentState = {
            "session_id": "test-session",
            "user_id": "test-user",
            "user_message": "Hello!",
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

    async def test_process_message_empty(self):
        """Should return error for empty message."""
        state: AgentState = {
            "session_id": "test-session",
            "user_id": "test-user",
            "user_message": "   ",
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
        # Mock the message repository
        with patch("app.agents.alfred.MessageRepository") as MockRepo:
            mock_repo = AsyncMock()
            mock_repo.get_recent_messages.return_value = []
            mock_repo.create_message.return_value = MagicMock(id="msg-id")
            MockRepo.return_value = mock_repo

            agent = AlfredAgent(db=mock_db, llm_provider=mock_provider)
            response = await agent.run(
                session_id="test-session",
                user_id="test-user",
                message="Hello!",
            )

            assert response == "Hello! How can I help you?"
            assert mock_repo.create_message.call_count == 2

    async def test_agent_stream(self, mock_db, mock_provider):
        """Should stream response tokens."""
        with patch("app.agents.alfred.MessageRepository") as MockRepo:
            mock_repo = AsyncMock()
            mock_repo.get_recent_messages.return_value = []
            mock_repo.create_message.return_value = MagicMock(id="msg-id")
            MockRepo.return_value = mock_repo

            agent = AlfredAgent(db=mock_db, llm_provider=mock_provider)

            tokens = []
            async for token in agent.stream(
                session_id="test-session",
                user_id="test-user",
                message="Hello!",
            ):
                tokens.append(token)

            assert len(tokens) > 0
            full_response = "".join(tokens)
            assert "Hello!" in full_response

    async def test_agent_empty_message(self, mock_db, mock_provider):
        """Should raise error for empty message."""
        with patch("app.agents.alfred.MessageRepository"):
            agent = AlfredAgent(db=mock_db, llm_provider=mock_provider)

            with pytest.raises(ValueError, match="Empty message"):
                await agent.run(
                    session_id="test-session",
                    user_id="test-user",
                    message="   ",
                )
