import logging
import re
from collections.abc import AsyncGenerator
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from app.agents.state import AgentState
from app.core.config import get_settings
from app.core.embeddings import get_embedding_provider
from app.core.llm import LLMMessage, LLMProvider, LLMResponse, ToolCall, get_llm_provider
from app.db.repositories import MemoryRepository, MessageRepository
from app.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)

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

**Voice:**
- You sound like a knowledgeable person having a conversation, not a reference document being read aloud. Even when using structure like lists, the surrounding prose should feel like *you* — someone with perspective, not a neutral encyclopedia.
- Lead with the answer, not commentary about the question.
- Be concise out of respect for the reader's time.
- You have a point of view. When something is good, say so. When something is overrated or has a catch, note it. Alfred wouldn't just list options neutrally — he'd guide you toward what actually matters.

**Personality — the seasoning, not the dish:**
- Dry wit shows up *inside* the substance — a wry parenthetical, a quietly opinionated aside, a small observation that makes someone smile. It's not a performance or a setup; it's just how you talk.
- Warmth comes through in attentiveness and tone, not in exclaiming about what they asked.
- "Sir" sparingly — an affectionate habit, not a verbal tic. Once or twice in a conversation, usually near the end, when it feels right.
- Close with a brief, genuine check-in when it fits naturally. Not every response needs one.

**What to avoid:**
- Flat, personality-free responses. If the answer could have come from any generic AI assistant, it needs more *you*.
- Commenting on the question ("Ah, Kubernetes!" / "A wise move, sir.")
- Preamble ("Let me think..." / "Great question!")
- Forced Britishisms ("I daresay" / "quite so" / "jolly good")
- Exaggerated butler mannerisms. You're inspired by Alfred, not doing an impression.
- Anthropomorphizing technology ("Kubernetes, in its wisdom...")
- Narrating transitions ("Now, shifting gears...")

**By format:**
- Technical questions: Answer directly, explain clearly, use structure when it helps. But frame and connect things in your own voice — the bits between the bullet points matter.
- Casual conversation: Warm, personable, brief but not curt. This is where the personality breathes most naturally.
- Complex topics: Break them down with the confidence of someone who's explained this before. You've seen a few things in your time."""


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
    today = datetime.now(timezone.utc).strftime("%B %d, %Y")
    system_content = SYSTEM_PROMPT
    system_content += f"\n\nToday's date is {today}."
    system_content += (
        "\n\n**Tool usage:** You have access to tools like web search. "
        "When you use a tool, review the results carefully and then respond to the user. "
        "One search is usually sufficient — do not repeat searches with slightly different queries. "
        "Use the results you have, even if they're imperfect."
    )
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


MAX_TOOL_ITERATIONS = 3


def _build_final_messages(messages: list[LLMMessage]) -> list[LLMMessage]:
    """
    Build clean messages for the final iteration when we need to force a text response.

    The plain stream()/generate() methods can't handle tool messages (ToolMessage
    requires tool definitions on the model). Instead, we inject tool results into
    the system prompt and keep only regular user/assistant messages.
    """
    clean: list[LLMMessage] = []
    tool_results: list[str] = []

    for msg in messages:
        if msg.role == "assistant" and msg.tool_calls:
            # Skip assistant messages that contain tool calls
            continue
        elif msg.role == "tool":
            # Collect tool results
            tool_results.append(msg.content or "(no result)")
        else:
            clean.append(LLMMessage(role=msg.role, content=msg.content))

    # Inject tool results into the system prompt
    if tool_results and clean and clean[0].role == "system":
        results_context = (
            "\n\n**Web search results (already retrieved for this conversation):**\n\n"
            + "\n\n---\n\n".join(tool_results)
            + "\n\nUse these search results to answer the user's question. "
            "Do not claim you cannot search the web — the search was already performed."
        )
        clean[0] = LLMMessage(
            role="system",
            content=(clean[0].content or "") + results_context,
        )

    return clean


async def generate_response_with_tools(
    state: AgentState,
    llm_provider: LLMProvider,
    tool_registry: ToolRegistry,
) -> dict[str, Any]:
    """
    Generate a response using the ReAct loop (non-streaming).
    The LLM can call tools, get results, and call again until it produces text.
    """
    if state.get("error"):
        return {}

    messages = build_prompt_messages(state)
    tool_defs = tool_registry.get_definitions()

    for iteration in range(MAX_TOOL_ITERATIONS):
        # On the last iteration, force a text-only response (no tools)
        is_last = iteration >= MAX_TOOL_ITERATIONS - 1

        logger.info(f"ReAct iteration {iteration + 1}/{MAX_TOOL_ITERATIONS}")

        try:
            if is_last:
                logger.info("Final iteration — calling LLM without tools to force text response")
                # Build clean messages that don't contain tool-specific types
                clean_messages = _build_final_messages(messages)
                text = await llm_provider.generate(clean_messages)
                return {"response": text}
            else:
                response = await llm_provider.generate_with_tools(messages, tool_defs)
        except Exception as e:
            logger.error(f"LLM error on iteration {iteration + 1}: {e}")
            return {"error": f"LLM error: {str(e)}"}

        if response.tool_calls:
            logger.info(
                f"Iteration {iteration + 1}: {len(response.tool_calls)} tool call(s): "
                f"{[tc.name for tc in response.tool_calls]}"
            )
            # Append assistant message with tool calls
            messages.append(LLMMessage(
                role="assistant",
                content=response.content,
                tool_calls=response.tool_calls,
            ))

            # Execute each tool and append results
            for tc in response.tool_calls:
                tool = tool_registry.get(tc.name)
                if tool:
                    logger.info(f"Executing tool '{tc.name}' with args: {tc.arguments}")
                    try:
                        result = await tool.execute(**tc.arguments)
                        logger.info(f"Tool '{tc.name}' returned {len(result)} chars")
                    except Exception as e:
                        logger.error(f"Tool '{tc.name}' execution error: {e}")
                        result = f"Tool error: {str(e)}"
                else:
                    result = f"Unknown tool: {tc.name}"

                messages.append(LLMMessage(
                    role="tool",
                    content=result,
                    tool_call_id=tc.id,
                ))
            continue

        # No tool calls — we have the final text response
        logger.info(f"ReAct completed on iteration {iteration + 1}")
        return {"response": response.content or ""}

    # Should not reach here, but just in case
    return {"response": "I wasn't able to complete that request."}


async def generate_response_stream_with_tools(
    state: AgentState,
    llm_provider: LLMProvider,
    tool_registry: ToolRegistry,
) -> AsyncGenerator[dict[str, Any], None]:
    """
    Generate a streaming response using the ReAct loop.
    Yields dict events: {"type": "token", "content": ...} or {"type": "tool_use", "tool_name": ...}
    """
    if state.get("error"):
        return

    messages = build_prompt_messages(state)
    tool_defs = tool_registry.get_definitions()
    any_text_yielded = False

    for iteration in range(MAX_TOOL_ITERATIONS):
        tool_calls_this_iteration: list[ToolCall] = []
        text_this_iteration: list[str] = []

        logger.info(f"ReAct stream iteration {iteration + 1}/{MAX_TOOL_ITERATIONS}")

        # On the last iteration, don't offer tools — force a text response
        if iteration >= MAX_TOOL_ITERATIONS - 1:
            logger.info("Final iteration — streaming without tools to force text response")
            # Build clean messages that don't contain tool-specific types
            clean_messages = _build_final_messages(messages)
            try:
                async for token in llm_provider.stream(clean_messages):
                    if token:
                        any_text_yielded = True
                        yield {"type": "token", "content": token}
            except Exception as e:
                logger.error(f"Final iteration stream error: {e}")
                yield {"type": "token", "content": f"I ran into an issue: {str(e)}"}
            return

        try:
            async for chunk in llm_provider.stream_with_tools(messages, tool_defs):
                if chunk.content:
                    text_this_iteration.append(chunk.content)
                    any_text_yielded = True
                    yield {"type": "token", "content": chunk.content}
                if chunk.tool_calls:
                    tool_calls_this_iteration.extend(chunk.tool_calls)
        except Exception as e:
            logger.error(f"stream_with_tools error on iteration {iteration + 1}: {e}")
            # If we already emitted some text, just stop. Otherwise yield the error.
            if not any_text_yielded:
                yield {"type": "token", "content": f"I ran into an issue: {str(e)}"}
            return

        if tool_calls_this_iteration:
            logger.info(
                f"Iteration {iteration + 1}: {len(tool_calls_this_iteration)} tool call(s): "
                f"{[tc.name for tc in tool_calls_this_iteration]}"
            )
            # Append assistant message with tool calls (include any text emitted)
            messages.append(LLMMessage(
                role="assistant",
                content="".join(text_this_iteration) if text_this_iteration else None,
                tool_calls=tool_calls_this_iteration,
            ))

            for tc in tool_calls_this_iteration:
                # Emit tool_use event for frontend
                yield {"type": "tool_use", "tool_name": tc.name}

                tool = tool_registry.get(tc.name)
                if tool:
                    logger.info(f"Executing tool '{tc.name}' with args: {tc.arguments}")
                    try:
                        result = await tool.execute(**tc.arguments)
                        logger.info(f"Tool '{tc.name}' returned {len(result)} chars")
                    except Exception as e:
                        logger.error(f"Tool '{tc.name}' execution error: {e}")
                        result = f"Tool error: {str(e)}"
                else:
                    result = f"Unknown tool: {tc.name}"

                messages.append(LLMMessage(
                    role="tool",
                    content=result,
                    tool_call_id=tc.id,
                ))
            continue

        # No tool calls — stream ended with text, we're done
        logger.info(
            f"ReAct stream completed on iteration {iteration + 1}, "
            f"text yielded: {any_text_yielded}"
        )
        return

    logger.warning("ReAct stream loop exhausted all iterations")


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
