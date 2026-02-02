import re
from collections.abc import AsyncGenerator
from typing import Any
from uuid import uuid4

from app.agents.state import AgentState
from app.core.config import get_settings
from app.core.embeddings import get_embedding_provider
from app.core.llm import LLMMessage, LLMProvider, get_llm_provider
from app.db.repositories import MemoryRepository, MessageRepository

# Pattern for /remember command
REMEMBER_COMMAND_PATTERN = re.compile(r"^/remember\s+(.+)$", re.IGNORECASE | re.DOTALL)

# Patterns for natural language memory save triggers
NATURAL_REMEMBER_PATTERNS = [
    re.compile(r"^remember\s+that\s+(.+)$", re.IGNORECASE | re.DOTALL),
    re.compile(r"^please\s+remember\s+that\s+(.+)$", re.IGNORECASE | re.DOTALL),
    re.compile(r"^save\s+to\s+memory[:\s]+(.+)$", re.IGNORECASE | re.DOTALL),
    re.compile(r"^save\s+this[:\s]+(.+)$", re.IGNORECASE | re.DOTALL),
    re.compile(r"^note\s+that\s+(.+)$", re.IGNORECASE | re.DOTALL),
    re.compile(r"^keep\s+in\s+mind\s+that\s+(.+)$", re.IGNORECASE | re.DOTALL),
]


def detect_remember_intent(message: str) -> tuple[bool, str | None]:
    """
    Detect if the message is a remember command or natural language save trigger.

    Returns:
        Tuple of (is_remember_intent, content_to_save)
    """
    message = message.strip()

    # Check /remember command first
    match = REMEMBER_COMMAND_PATTERN.match(message)
    if match:
        return True, match.group(1).strip()

    # Check natural language patterns
    for pattern in NATURAL_REMEMBER_PATTERNS:
        match = pattern.match(message)
        if match:
            return True, match.group(1).strip()

    return False, None


def infer_memory_type(content: str) -> str:
    """
    Infer the memory type from the content.

    Returns one of: 'preference', 'knowledge', 'summary'
    """
    content_lower = content.lower()

    # Preference indicators
    preference_keywords = [
        "i prefer",
        "i like",
        "i don't like",
        "i hate",
        "i love",
        "i want",
        "i always",
        "i never",
        "my favorite",
        "my preferred",
    ]
    for keyword in preference_keywords:
        if keyword in content_lower:
            return "preference"

    # Default to knowledge for factual statements
    return "knowledge"


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
    Validates input, detects /remember commands, and prepares state.
    """
    user_message = state.get("user_message", "").strip()

    if not user_message:
        return {"error": "Empty message"}

    # Detect remember intent
    is_remember, remember_content = detect_remember_intent(user_message)

    return {
        "user_message": user_message,
        "user_message_id": str(uuid4()),
        "assistant_message_id": str(uuid4()),
        "is_remember_command": is_remember,
        "remember_content": remember_content,
        "error": None,
    }


async def handle_remember_command(
    state: AgentState,
    memory_repo: MemoryRepository,
) -> dict[str, Any]:
    """
    Handle a /remember command or natural language memory save.

    Saves the content as a memory and returns a confirmation response.
    """
    remember_content = state.get("remember_content")
    if not remember_content:
        return {"error": "No content to remember"}

    user_id = state["user_id"]
    session_id = state["session_id"]

    # Infer memory type from content
    memory_type = infer_memory_type(remember_content)

    # Generate embedding
    embedding_provider = get_embedding_provider()
    embedding = embedding_provider.embed(remember_content)

    # Check for duplicates
    settings = get_settings()
    existing = await memory_repo.find_duplicate(
        user_id=user_id,
        embedding=embedding,
        threshold=settings.memory_similarity_threshold,
    )

    if existing:
        return {
            "response": (
                "I believe I already have that noted, sir. "
                f"I have recorded: \"{existing.content}\""
            ),
            "memory_saved": False,
        }

    # Save the memory
    await memory_repo.create_memory(
        user_id=user_id,
        type=memory_type,
        content=remember_content,
        embedding=embedding,
        source_session_id=session_id,
    )

    return {
        "response": (
            f"Very good, sir. I shall remember that: \"{remember_content}\""
        ),
        "memory_saved": True,
    }


async def retrieve_context(
    state: AgentState,
    message_repo: MessageRepository,
    memory_repo: MemoryRepository | None = None,
) -> dict[str, Any]:
    """
    Retrieve recent messages and relevant memories for context.

    Uses semantic search via pgvector to find memories relevant to
    the current user message.
    """
    session_id = state["session_id"]
    user_id = state["user_id"]
    user_message = state.get("user_message", "")

    # Get recent messages from the session
    recent_messages = await message_repo.get_recent_messages(
        session_id=session_id,
        limit=10,
    )

    context_messages = [
        {"role": msg.role, "content": msg.content}
        for msg in recent_messages
    ]

    # Retrieve relevant memories via semantic search
    memories: list[str] = []
    if memory_repo and user_message:
        settings = get_settings()
        embedding_provider = get_embedding_provider()

        # Generate embedding for the user's message
        query_embedding = embedding_provider.embed(user_message)

        # Search for similar memories
        similar_memories = await memory_repo.search_similar(
            user_id=user_id,
            query_embedding=query_embedding,
            limit=settings.memory_retrieval_limit,
        )

        # Extract content from matched memories
        memories = [memory.content for memory, _score in similar_memories]

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
