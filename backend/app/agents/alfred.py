from collections.abc import AsyncGenerator
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.nodes import (
    extract_memories,
    generate_response,
    generate_response_stream,
    handle_remember_command,
    process_message,
    retrieve_context,
    save_assistant_message,
    save_user_message,
)
from app.agents.state import AgentState
from app.core.llm import LLMProvider, get_llm_provider
from app.db.repositories import MemoryRepository, MessageRepository


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
        self.memory_repo = MemoryRepository(db)

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

        # Step 1: Process message (detects /remember commands)
        state.update(await process_message(state))
        if state.get("error"):
            raise ValueError(state["error"])

        # Step 1b: Handle /remember command if detected
        if state.get("is_remember_command"):
            state.update(
                await handle_remember_command(state, self.memory_repo)
            )
            # Save messages and return early
            await save_user_message(state, self.message_repo)
            await save_assistant_message(state, self.message_repo)
            return state["response"]

        # Step 2: Retrieve context (includes memory retrieval)
        state.update(
            await retrieve_context(state, self.message_repo, self.memory_repo)
        )

        # Step 3: Save user message (after context retrieval, before response generation)
        # This ensures user message has earlier timestamp than assistant response
        await save_user_message(state, self.message_repo)

        # Step 4: Generate response
        state.update(await generate_response(state, self.llm_provider))
        if state.get("error"):
            raise ValueError(state["error"])

        # Step 5: Extract memories (handled by scheduled task)
        state.update(await extract_memories(state))

        # Step 6: Save assistant message
        await save_assistant_message(state, self.message_repo)

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

        # Step 1: Process message (detects /remember commands)
        state.update(await process_message(state))
        if state.get("error"):
            raise ValueError(state["error"])

        # Step 1b: Handle /remember command if detected
        if state.get("is_remember_command"):
            state.update(
                await handle_remember_command(state, self.memory_repo)
            )
            # Yield the response and save messages
            yield state["response"]
            await save_user_message(state, self.message_repo)
            await save_assistant_message(state, self.message_repo)
            return

        # Step 2: Retrieve context (includes memory retrieval)
        state.update(
            await retrieve_context(state, self.message_repo, self.memory_repo)
        )

        # Step 3: Save user message (after context retrieval, before response generation)
        # This ensures user message has earlier timestamp than assistant response
        await save_user_message(state, self.message_repo)

        # Step 4: Generate streaming response
        full_response: list[str] = []
        async for token in generate_response_stream(state, self.llm_provider):
            full_response.append(token)
            yield token

        # Collect full response for saving
        state["response"] = "".join(full_response)

        # Step 5: Extract memories (handled by scheduled task)
        await extract_memories(state)

        # Step 6: Save assistant message
        await save_assistant_message(state, self.message_repo)
