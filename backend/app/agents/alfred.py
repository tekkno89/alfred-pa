from collections.abc import AsyncGenerator
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.state import AgentState
from app.agents.nodes import (
    build_prompt_messages,
    extract_memories,
    generate_response,
    generate_response_stream,
    process_message,
    retrieve_context,
    save_messages,
)
from app.core.llm import LLMProvider, get_llm_provider
from app.db.repositories import MessageRepository


class AlfredAgent:
    """
    Alfred AI Assistant agent.

    Handles conversation flow:
    1. Process incoming message
    2. Retrieve context (history + memories)
    3. Generate response (streaming or non-streaming)
    4. Extract memories (placeholder for Phase 4)
    5. Save messages to database
    """

    def __init__(
        self,
        db: AsyncSession,
        llm_provider: LLMProvider | None = None,
    ):
        self.db = db
        self.llm_provider = llm_provider or get_llm_provider()
        self.message_repo = MessageRepository(db)

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
        state: AgentState = {
            "session_id": session_id,
            "user_id": user_id,
            "user_message": message,
            "context_messages": [],
            "memories": [],
            "response": "",
            "response_chunks": [],
            "user_message_id": "",
            "assistant_message_id": "",
            "error": None,
        }

        # Step 1: Process message
        state.update(await process_message(state))
        if state.get("error"):
            raise ValueError(state["error"])

        # Step 2: Retrieve context
        state.update(await retrieve_context(state, self.message_repo))

        # Step 3: Generate response
        state.update(await generate_response(state, self.llm_provider))
        if state.get("error"):
            raise ValueError(state["error"])

        # Step 4: Extract memories (placeholder)
        state.update(await extract_memories(state))

        # Step 5: Save messages
        state.update(await save_messages(state, self.message_repo))

        return state["response"]

    async def stream(
        self,
        session_id: str,
        user_id: str,
        message: str,
    ) -> AsyncGenerator[str, None]:
        """
        Run the agent with streaming response.

        Args:
            session_id: The session ID
            user_id: The user ID
            message: The user's message

        Yields:
            Response tokens as they are generated
        """
        state: AgentState = {
            "session_id": session_id,
            "user_id": user_id,
            "user_message": message,
            "context_messages": [],
            "memories": [],
            "response": "",
            "response_chunks": [],
            "user_message_id": "",
            "assistant_message_id": "",
            "error": None,
        }

        # Step 1: Process message
        state.update(await process_message(state))
        if state.get("error"):
            raise ValueError(state["error"])

        # Step 2: Retrieve context
        state.update(await retrieve_context(state, self.message_repo))

        # Step 3: Generate streaming response
        full_response: list[str] = []
        async for token in generate_response_stream(state, self.llm_provider):
            full_response.append(token)
            yield token

        # Collect full response for saving
        state["response"] = "".join(full_response)

        # Step 4: Extract memories (placeholder)
        await extract_memories(state)

        # Step 5: Save messages
        await save_messages(state, self.message_repo)
