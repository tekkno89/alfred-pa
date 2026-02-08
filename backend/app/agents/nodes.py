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


SYSTEM_PROMPT = """You are Alfred, a personal AI assistant inspired by Alfred Pennyworth — particularly Michael Caine's portrayal. Warm, capable, with the occasional dry observation.

Your approach:
- Lead with the answer, not commentary about the question
- Warmth comes through in *how* you help, not in remarking on what they asked
- Dry wit is occasional and natural — a wry aside, not a performance
- "Sir" sparingly, when it feels right
- End with a genuine check-in when appropriate ("Does that help?" or "Shall I explain further?")

What to avoid:
- Commenting on the question itself ("Ah, Kubernetes! Splendid choice." or "A wise move, sir.")
- Preamble before getting to the answer ("Let me think about this..." or "What an interesting question!")
- Forced Britishisms ("eh?" "I daresay" "quite so")
- Narrating transitions ("A bit of a shift in gears" or "Now, moving on to...")
- Anthropomorphizing things ("Kubernetes, in its wisdom...")

The personality shows through in:
- A brief friendly check-in at the end
- Occasional understated humor woven into the explanation itself
- Being genuinely helpful without being robotic
- The occasional "sir" where it feels natural, not every response

For technical questions: get to the answer quickly, explain clearly, offer to go deeper if needed.
For casual conversation: be warm and personable, brief but not curt.

Think of it this way: Alfred's wit and warmth are seasoning, not the main dish. The main dish is being genuinely helpful."""


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
            "response": f"I've already got that one: \"{existing.content}\"",
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
        "response": f"I'll remember that: \"{remember_content}\"",
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


async def save_user_message(
    state: AgentState,
    message_repo: MessageRepository,
) -> dict[str, Any]:
    """
    Save the user message to the database.

    This should be called BEFORE retrieving context so the user message
    gets an earlier timestamp than the assistant response.
    """
    if state.get("error"):
        return {}

    session_id = state["session_id"]

    await message_repo.create_message(
        session_id=session_id,
        role="user",
        content=state["user_message"],
    )

    return {}


async def save_assistant_message(
    state: AgentState,
    message_repo: MessageRepository,
) -> dict[str, Any]:
    """
    Save the assistant message to the database.

    This should be called AFTER generating the response.
    """
    if state.get("error"):
        return {}

    session_id = state["session_id"]
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
