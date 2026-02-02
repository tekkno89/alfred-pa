from collections.abc import AsyncGenerator
from typing import Any
from uuid import uuid4

from app.agents.state import AgentState
from app.core.llm import LLMMessage, LLMProvider, get_llm_provider
from app.db.repositories import MessageRepository, SessionRepository


SYSTEM_PROMPT = """You are Alfred, a personal AI assistant modeled after Alfred Pennyworth — the legendary butler known for his unwavering loyalty, dry wit, and quiet brilliance.

Your personality:
- Refined and eloquent, with impeccable manners and a touch of British formality
- Warm yet dignified — you genuinely care, but maintain professional composure
- Dry, understated humor — a well-timed quip or gentle sarcasm when appropriate
- Unflappable in crisis — calm, reassuring, and pragmatic under pressure
- Quietly wise — you offer sage advice without being preachy

Your approach:
- Address the user with respect, occasionally using "sir" or "madam" if it feels natural
- Be helpful and thorough, but never servile — you have your own opinions and aren't afraid to express them diplomatically
- When the user is about to make a questionable decision, gently raise concerns with tact
- Celebrate their successes with understated pride ("Well done, if I may say so")
- If you don't know something, admit it gracefully ("I'm afraid that's beyond my current knowledge, though I'd be happy to help you investigate")

Communication style:
- Clear and articulate, favoring quality over brevity
- Use markdown formatting when it aids clarity
- Offer thoughtful follow-up suggestions
- A touch of warmth beneath the formality — you're not cold, just proper"""


async def process_message(state: AgentState) -> dict[str, Any]:
    """
    Process the incoming user message.
    Validates input and prepares state.
    """
    user_message = state.get("user_message", "").strip()

    if not user_message:
        return {"error": "Empty message"}

    return {
        "user_message": user_message,
        "user_message_id": str(uuid4()),
        "assistant_message_id": str(uuid4()),
        "error": None,
    }


async def retrieve_context(
    state: AgentState,
    message_repo: MessageRepository,
) -> dict[str, Any]:
    """
    Retrieve recent messages for context.
    """
    session_id = state["session_id"]

    # Get recent messages from the session
    recent_messages = await message_repo.get_recent_messages(
        session_id=session_id,
        limit=10,
    )

    context_messages = [
        {"role": msg.role, "content": msg.content}
        for msg in recent_messages
    ]

    # TODO: In Phase 4, also retrieve relevant memories via semantic search
    memories: list[str] = []

    return {
        "context_messages": context_messages,
        "memories": memories,
    }


def build_prompt_messages(state: AgentState) -> list[LLMMessage]:
    """Build the list of messages for the LLM."""
    messages: list[LLMMessage] = []

    # System prompt
    system_content = SYSTEM_PROMPT
    if state.get("memories"):
        memory_context = "\n\nRelevant context about the user:\n" + "\n".join(
            f"- {m}" for m in state["memories"]
        )
        system_content += memory_context

    messages.append(LLMMessage(role="system", content=system_content))

    # Add conversation history
    for msg in state.get("context_messages", []):
        role = msg["role"]
        if role in ("user", "assistant"):
            messages.append(LLMMessage(role=role, content=msg["content"]))  # type: ignore

    # Add current user message
    messages.append(LLMMessage(role="user", content=state["user_message"]))

    return messages


async def generate_response(
    state: AgentState,
    llm_provider: LLMProvider | None = None,
) -> dict[str, Any]:
    """
    Generate a response using the LLM (non-streaming).
    """
    if state.get("error"):
        return {}

    provider = llm_provider or get_llm_provider()
    messages = build_prompt_messages(state)

    try:
        response = await provider.generate(messages)
        return {"response": response}
    except Exception as e:
        return {"error": f"LLM error: {str(e)}"}


async def generate_response_stream(
    state: AgentState,
    llm_provider: LLMProvider | None = None,
) -> AsyncGenerator[str, None]:
    """
    Generate a streaming response using the LLM.
    Yields tokens as they arrive.
    """
    if state.get("error"):
        return

    provider = llm_provider or get_llm_provider()
    messages = build_prompt_messages(state)

    async for token in provider.stream(messages):
        yield token


async def save_messages(
    state: AgentState,
    message_repo: MessageRepository,
) -> dict[str, Any]:
    """
    Save user and assistant messages to the database.
    """
    if state.get("error"):
        return {}

    session_id = state["session_id"]

    # Save user message
    await message_repo.create_message(
        session_id=session_id,
        role="user",
        content=state["user_message"],
    )

    # Save assistant response
    response = state.get("response", "")
    if response:
        await message_repo.create_message(
            session_id=session_id,
            role="assistant",
            content=response,
        )

    return {}


async def extract_memories(state: AgentState) -> dict[str, Any]:
    """
    Extract memories from the conversation.
    TODO: Implement in Phase 4 (Memory System).
    """
    # Placeholder - will be implemented in Phase 4
    return {}
