import logging
import re
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from langchain_core.runnables import RunnableConfig
from langgraph.config import get_stream_writer

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

MAX_TOOL_ITERATIONS = 3


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
        "Don't repeat the exact same query, but do refine and search again when needed — "
        "multiple searches help for complex multi-faceted questions, when initial results "
        "are incomplete or conflicting, or when comparing different topics. "
        "You have up to 3 tool iterations, so be strategic with your searches."
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


# ---------------------------------------------------------------------------
# Graph node functions
# ---------------------------------------------------------------------------


async def process_message_node(state: AgentState, config: RunnableConfig) -> dict[str, Any]:
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


async def handle_remember_node(state: AgentState, config: RunnableConfig) -> dict[str, Any]:
    """
    Handle a /remember command or natural language memory save.
    Saves the content as a memory and returns a confirmation response.
    """
    db = config["configurable"]["db"]
    memory_repo = MemoryRepository(db)

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
        response = f'I\'ve already got that one: "{existing.content}"'
    else:
        await memory_repo.create_memory(
            user_id=user_id,
            type=memory_type,
            content=remember_content,
            embedding=embedding,
            source_session_id=session_id,
        )
        response = f'I\'ll remember that: "{remember_content}"'

    # Stream the response if in streaming mode
    streaming = config["configurable"].get("streaming", False)
    if streaming:
        writer = get_stream_writer()
        writer({"type": "token", "content": response})

    return {"response": response}


async def retrieve_context_node(state: AgentState, config: RunnableConfig) -> dict[str, Any]:
    """
    Retrieve recent messages and relevant memories for context.
    """
    db = config["configurable"]["db"]
    message_repo = MessageRepository(db)
    memory_repo = MemoryRepository(db)

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
    if user_message:
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


async def save_user_message_node(state: AgentState, config: RunnableConfig) -> dict[str, Any]:
    """Save the user message to the database."""
    if state.get("error"):
        return {}

    db = config["configurable"]["db"]
    message_repo = MessageRepository(db)

    await message_repo.create_message(
        session_id=state["session_id"],
        role="user",
        content=state["user_message"],
    )

    return {}


async def save_assistant_message_node(state: AgentState, config: RunnableConfig) -> dict[str, Any]:
    """Save the assistant message to the database."""
    if state.get("error"):
        return {}

    db = config["configurable"]["db"]
    message_repo = MessageRepository(db)

    response = state.get("response", "")
    if response:
        # Include tool results metadata if any tools were executed
        metadata = None
        tool_results = state.get("tool_results_metadata")
        if tool_results:
            metadata = {"tool_results": tool_results}

        await message_repo.create_message(
            session_id=state["session_id"],
            role="assistant",
            content=response,
            metadata=metadata,
        )

    return {}


async def save_messages_node(state: AgentState, config: RunnableConfig) -> dict[str, Any]:
    """Save both user and assistant messages (for the remember path)."""
    if state.get("error"):
        return {}

    db = config["configurable"]["db"]
    message_repo = MessageRepository(db)

    await message_repo.create_message(
        session_id=state["session_id"],
        role="user",
        content=state["user_message"],
    )

    response = state.get("response", "")
    if response:
        await message_repo.create_message(
            session_id=state["session_id"],
            role="assistant",
            content=response,
        )

    return {}


async def llm_node(state: AgentState, config: RunnableConfig) -> dict[str, Any]:
    """
    Call the LLM, with or without tools.

    On first call (llm_messages empty), builds the prompt from state.
    On subsequent calls (after tool execution), uses the existing llm_messages.
    On the final iteration, calls without tools to force a text response.
    """
    if state.get("error"):
        return {}

    configurable = config["configurable"]
    llm_provider: LLMProvider = configurable["llm_provider"]
    tool_registry: ToolRegistry = configurable["tool_registry"]
    streaming = configurable.get("streaming", False)

    # Build or reuse llm_messages
    llm_messages = list(state.get("llm_messages") or [])
    if not llm_messages:
        llm_messages = build_prompt_messages(state)

    tool_iteration = state.get("tool_iteration", 0)
    has_tools = tool_registry.has_tools()
    is_last_iteration = tool_iteration >= MAX_TOOL_ITERATIONS - 1

    # Decide whether to use tools
    use_tools = has_tools and not is_last_iteration

    if use_tools:
        tool_defs = tool_registry.get_definitions()

        if streaming:
            writer = get_stream_writer()
            tool_calls_this_iteration: list[ToolCall] = []
            text_parts: list[str] = []

            try:
                async for chunk in llm_provider.stream_with_tools(llm_messages, tool_defs):
                    if chunk.content:
                        text_parts.append(chunk.content)
                        writer({"type": "token", "content": chunk.content})
                    if chunk.tool_calls:
                        tool_calls_this_iteration.extend(chunk.tool_calls)
            except Exception as e:
                logger.error(f"stream_with_tools error: {e}")
                return {"error": f"LLM error: {str(e)}"}

            if tool_calls_this_iteration:
                # Append assistant message with tool calls
                llm_messages.append(LLMMessage(
                    role="assistant",
                    content="".join(text_parts) if text_parts else None,
                    tool_calls=tool_calls_this_iteration,
                ))
                return {
                    "llm_messages": llm_messages,
                    "tool_calls": tool_calls_this_iteration,
                }
            else:
                # No tool calls — final text response
                return {
                    "response": "".join(text_parts),
                    "llm_messages": llm_messages,
                    "tool_calls": None,
                }
        else:
            # Non-streaming with tools
            try:
                response = await llm_provider.generate_with_tools(llm_messages, tool_defs)
            except Exception as e:
                logger.error(f"generate_with_tools error: {e}")
                return {"error": f"LLM error: {str(e)}"}

            if response.tool_calls:
                llm_messages.append(LLMMessage(
                    role="assistant",
                    content=response.content,
                    tool_calls=response.tool_calls,
                ))
                return {
                    "llm_messages": llm_messages,
                    "tool_calls": response.tool_calls,
                }
            else:
                return {
                    "response": response.content or "",
                    "llm_messages": llm_messages,
                    "tool_calls": None,
                }
    else:
        # No tools or last iteration — force text response
        if is_last_iteration and has_tools:
            logger.info("Final iteration — calling LLM without tools to force text response")
            clean_messages = _build_final_messages(llm_messages)
        else:
            clean_messages = llm_messages

        if streaming:
            writer = get_stream_writer()
            text_parts = []
            try:
                async for token in llm_provider.stream(clean_messages):
                    if token:
                        text_parts.append(token)
                        writer({"type": "token", "content": token})
            except Exception as e:
                logger.error(f"stream error: {e}")
                return {"error": f"LLM error: {str(e)}"}
            return {
                "response": "".join(text_parts),
                "llm_messages": llm_messages,
                "tool_calls": None,
            }
        else:
            try:
                text = await llm_provider.generate(clean_messages)
            except Exception as e:
                logger.error(f"generate error: {e}")
                return {"error": f"LLM error: {str(e)}"}
            return {
                "response": text,
                "llm_messages": llm_messages,
                "tool_calls": None,
            }


async def tool_node(state: AgentState, config: RunnableConfig) -> dict[str, Any]:
    """
    Execute tool calls from the LLM, append results to llm_messages,
    increment tool_iteration, and clear tool_calls.
    """
    configurable = config["configurable"]
    tool_registry: ToolRegistry = configurable["tool_registry"]
    streaming = configurable.get("streaming", False)

    tool_calls = state.get("tool_calls") or []
    llm_messages = list(state.get("llm_messages") or [])
    tool_iteration = state.get("tool_iteration", 0)
    tool_results_metadata = list(state.get("tool_results_metadata") or [])

    if streaming:
        writer = get_stream_writer()

    for tc in tool_calls:
        if streaming:
            writer({"type": "tool_use", "tool_name": tc.name, "tool_args": tc.arguments})

        tool = tool_registry.get(tc.name)
        if tool:
            logger.info(f"Executing tool '{tc.name}' with args: {tc.arguments}")
            try:
                result = await tool.execute(**tc.arguments)
                logger.info(f"Tool '{tc.name}' returned {len(result)} chars")
            except Exception as e:
                logger.error(f"Tool '{tc.name}' execution error: {e}")
                result = f"Tool error: {str(e)}"

            if tool.last_execution_metadata:
                metadata_entry = {
                    "tool_name": tc.name,
                    **tool.last_execution_metadata,
                }
                # Replace any existing entry for this tool name
                tool_results_metadata = [
                    m for m in tool_results_metadata if m.get("tool_name") != tc.name
                ]
                tool_results_metadata.append(metadata_entry)

                if streaming:
                    writer({
                        "type": "tool_result",
                        "tool_name": tc.name,
                        "tool_data": tool.last_execution_metadata,
                    })
                tool.last_execution_metadata = None
        else:
            result = f"Unknown tool: {tc.name}"

        llm_messages.append(LLMMessage(
            role="tool",
            content=result,
            tool_call_id=tc.id,
        ))

    return {
        "llm_messages": llm_messages,
        "tool_calls": None,
        "tool_iteration": tool_iteration + 1,
        "tool_results_metadata": tool_results_metadata if tool_results_metadata else None,
    }


async def extract_memories_node(state: AgentState, config: RunnableConfig) -> dict[str, Any]:
    """
    Extract memories from the conversation.
    TODO: Implement in Phase 4 (Memory System).
    """
    return {}


# ---------------------------------------------------------------------------
# Routing functions
# ---------------------------------------------------------------------------


def route_after_process(state: AgentState) -> str:
    """Route after process_message: remember path or normal path."""
    if state.get("error"):
        # Error state — go to END (handled by the graph edge)
        return "end"
    if state.get("is_remember_command"):
        return "handle_remember"
    return "retrieve_context"


def route_after_llm(state: AgentState) -> str:
    """Route after llm_node: tool execution or finish."""
    if state.get("tool_calls"):
        return "tool_node"
    return "extract_memories"


# ---------------------------------------------------------------------------
# Legacy function kept for backward compatibility with tests
# ---------------------------------------------------------------------------


async def process_message(state: AgentState) -> dict[str, Any]:
    """
    Process the incoming user message (legacy wrapper).
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
