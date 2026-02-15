from collections.abc import AsyncGenerator
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.graph import create_agent_graph
from app.agents.state import AgentState
from app.core.llm import LLMProvider, get_llm_provider
from app.tools.registry import ToolRegistry, get_tool_registry


class AlfredAgent:
    """
    Alfred AI Assistant agent.

    Uses a LangGraph StateGraph for orchestration:
    1. Process incoming message
    2. Retrieve context (history + memories)
    3. Generate response via ReAct loop (streaming or non-streaming)
    4. Extract memories (placeholder for Phase 4)
    5. Save messages to database
    """

    def __init__(
        self,
        db: AsyncSession,
        llm_provider: LLMProvider | None = None,
        tool_registry: ToolRegistry | None = None,
    ):
        self.db = db
        self.llm_provider = llm_provider or get_llm_provider()
        self.tool_registry = tool_registry or get_tool_registry()
        self.graph = create_agent_graph()

    def _initial_state(self, session_id: str, user_id: str, message: str) -> AgentState:
        """Build the initial state dict for a graph invocation."""
        return {
            "session_id": session_id,
            "user_id": user_id,
            "user_message": message,
            "is_remember_command": False,
            "remember_content": None,
            "context_messages": [],
            "memories": [],
            "response": "",
            "llm_messages": [],
            "tool_calls": None,
            "tool_iteration": 0,
            "user_message_id": "",
            "assistant_message_id": "",
            "error": None,
        }

    def _config(self, streaming: bool = False) -> dict:
        """Build the config dict for a graph invocation."""
        return {
            "configurable": {
                "db": self.db,
                "llm_provider": self.llm_provider,
                "tool_registry": self.tool_registry,
                "streaming": streaming,
            },
            "recursion_limit": 25,
        }

    async def run(
        self,
        session_id: str,
        user_id: str,
        message: str,
    ) -> str:
        """
        Run the agent and return the full response.

        Args:
            session_id: The session ID
            user_id: The user ID
            message: The user's message

        Returns:
            The assistant's response
        """
        state = self._initial_state(session_id, user_id, message)
        config = self._config(streaming=False)

        final_state = await self.graph.ainvoke(state, config)

        if final_state.get("error"):
            raise ValueError(final_state["error"])

        return final_state["response"]

    async def stream(
        self,
        session_id: str,
        user_id: str,
        message: str,
    ) -> AsyncGenerator[dict[str, Any], None]:
        """
        Run the agent with streaming response.

        Args:
            session_id: The session ID
            user_id: The user ID
            message: The user's message

        Yields:
            Event dicts: {"type": "token", "content": ...} or {"type": "tool_use", "tool_name": ...}
        """
        if not message.strip():
            raise ValueError("Empty message")

        state = self._initial_state(session_id, user_id, message)
        config = self._config(streaming=True)

        async for event in self.graph.astream(state, config, stream_mode="custom"):
            yield event
