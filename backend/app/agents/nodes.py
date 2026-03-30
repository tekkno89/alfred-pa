import logging
import re
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4
from zoneinfo import ZoneInfo

from langchain_core.runnables import RunnableConfig
from langgraph.config import get_stream_writer

from app.agents.state import AgentState
from app.core.config import get_settings
from app.core.llm import LLMMessage, LLMProvider, LLMResponse, ToolCall, get_llm_provider
from app.core.summarize import summarize_messages
from app.core.tokens import count_messages_tokens, count_tokens, get_context_limit
from app.db.repositories import MessageRepository, SessionRepository
from app.tools.base import ToolContext
from app.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)

DEFAULT_MAX_TOOL_ITERATIONS = 3
ABSOLUTE_MAX_TOOL_ITERATIONS = 8

# Regex patterns for XML/text artifacts that LLMs (especially Gemini) sometimes
# emit as raw text instead of using the structured tool calling API.
_XML_ARTIFACT_PATTERNS = [
    # Thinking / reasoning tags
    re.compile(r"<thinking>.*?</thinking>", re.DOTALL),
    re.compile(r"<antml_thinking>.*?</antml_thinking>", re.DOTALL),
    # Legacy function call XML
    re.compile(r"<function_calls>.*?</function_calls>", re.DOTALL),
    re.compile(r"<invoke\b[^>]*>.*?</invoke>", re.DOTALL),
    # Gemini-style tool call/result XML
    re.compile(r"<tool_call>.*?</tool_call>", re.DOTALL),
    re.compile(r"<tool_results>.*?</tool_results>", re.DOTALL),
    re.compile(r"<tool_result>.*?</tool_result>", re.DOTALL),
    re.compile(r"<tool_response>.*?</tool_response>", re.DOTALL),
]


def _sanitize_response(text: str) -> str:
    """Strip XML artifacts (thinking tags, fake tool calls) that the LLM may emit as text."""
    for pattern in _XML_ARTIFACT_PATTERNS:
        text = pattern.sub("", text)
    # Collapse multiple blank lines left behind after stripping
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


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


def build_prompt_messages(state: AgentState, *, tz: str | None = None) -> list[LLMMessage]:
    """Build the list of messages for the LLM."""
    messages: list[LLMMessage] = []

    # System prompt — use the user's local timezone when available
    user_tz = ZoneInfo(tz) if tz else timezone.utc
    now_local = datetime.now(user_tz)
    today = now_local.strftime("%B %d, %Y")
    # Include numeric UTC offset so the LLM knows the exact offset for todos
    utc_offset = now_local.strftime("%z")  # e.g. "-0800"
    utc_offset_formatted = f"{utc_offset[:3]}:{utc_offset[3:]}"  # e.g. "-08:00"
    current_time = now_local.strftime("%I:%M %p %Z") + f" (UTC{utc_offset_formatted})"
    # Build a dynamic example timestamp using today's actual offset (for todos)
    todo_example_ts = f"2026-03-15T09:00:00{utc_offset_formatted}"
    system_content = SYSTEM_PROMPT
    system_content += f"\n\nToday's date is {today}. The current time is {current_time}."
    system_content += (
        "\n\n**Tool usage:** You have access to tools like web search, focus mode management, todo management, and calendar management. "
        "When the user asks to enable/disable focus mode, start a pomodoro, check focus status, "
        "or skip a pomodoro phase, use the focus_mode tool. "
        "When the user asks to create, list, update, complete, or delete todos/tasks, use the manage_todos tool. "
        "For todo due dates, always use ISO 8601 format with the user's timezone offset "
        f"(e.g. {todo_example_ts}). Do NOT convert to UTC — use the offset that matches the current time shown above. "
        "For recurring todos, convert natural language recurrence to RFC 5545 RRULE strings "
        "(e.g. 'every day' -> 'FREQ=DAILY;INTERVAL=1', 'every weekday' -> 'FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR'). "
        "When you use a tool, review the results carefully and then respond to the user. "
        "Don't repeat the exact same query, but do refine and search again when needed — "
        "multiple searches help for complex multi-faceted questions, when initial results "
        "are incomplete or conflicting, or when comparing different topics. "
        "Be strategic with your tool calls.\n\n"
        "**Important:** Never fabricate or invent information that was not returned by a tool. "
        "If a tool returns an error, no results, or incomplete data, tell the user honestly "
        "what happened. It is far better to say \"I couldn't retrieve that data\" than to "
        "make up a plausible-sounding answer.\n\n"
        "When operating on todos:\n"
        "- Only operate on open/active todos unless the user explicitly asks about completed ones.\n"
        "- If a user asks to modify a todo and there are multiple open todos with the same or similar title, "
        "list them with their IDs and ask which one they mean before making changes.\n"
        "- If the conversation context includes a specific todo ID, always use that ID — do not create a new todo.\n\n"
        "When the user asks about their calendar, events, schedule, meetings, or appointments, "
        "use the manage_calendar tool. "
        "For calendar dates/times, use LOCAL time in ISO 8601 format WITHOUT a timezone offset "
        "(e.g. 2026-03-15T09:00:00). The tool automatically applies the user's timezone — "
        "do NOT append a UTC offset like -07:00 or -08:00. "
        "When creating events, default to calendar_id='primary'. Do NOT pass account_label unless the user explicitly specifies which account to use. "
        "If the user has multiple Google Calendar accounts, ask which account to use when ambiguous. "
        "When listing events, include the event ID so the user can reference it for updates or deletion. "
        "For recurring events, use scope='this' to modify a single instance or scope='all' for all instances.\n\n"
        "When the user asks to add a YouTube video to their queue, watch later, or manage YouTube playlists, "
        "use the manage_youtube tool. For add_video, only youtube_url is required — it defaults to the active playlist. "
        "If no playlist exists, one will be created automatically.\n\n"
        "When the user asks to search Slack, find messages, read conversations, or asks about what was discussed "
        "in a channel, use the slack_messages tool.\n"
        "For SEARCHING messages (action=\"search\"):\n"
        "- Start with scope=\"frequent\" to search the user's most active channels first.\n"
        "- If no results are found, tell the user the search was limited to their regular channels and "
        "ask if they want to expand (scope=\"all\").\n"
        "- If still not found and no date range was specified, ask the user for an approximate timeframe.\n"
        "- If results are ambiguous, present the top options as a numbered list and offer to continue searching.\n"
        "- Always include the permalink so the user can jump to the message in Slack.\n"
        "For READING conversations (action=\"get_messages\"):\n"
        "- Use this when the user wants to read, summarize, or extract information from a channel or DM conversation.\n"
        "- If the user names a specific channel, use get_messages directly with channel_name — "
        "it resolves names automatically via the Slack API, including private channels the user belongs to. "
        "You do NOT need to look up the channel_id first.\n"
        "- You can read full conversations and then create todos, calendar events, summaries, or use the content for other tasks.\n"
        "- Use thread_ts to read a specific thread's replies.\n"
        "- Use include_replies=true when the user wants to see full threaded discussions.\n"
        "For BROWSING top channels (action=\"top_channels\"):\n"
        "- Shows only the user's most active channels from cached data — this is NOT an exhaustive list of all channels.\n"
        "- Useful when the user wants to browse their frequent channels or isn't sure which channel to look at.\n"
        "- Do NOT rely on this as the source of truth for whether a channel exists.\n"
        "For FINDING a channel (action=\"find_channel\"):\n"
        "- Searches the live Slack API for channels matching a name or partial name.\n"
        "- Use this when you need to verify a channel exists, find channels matching a keyword, "
        "or when a channel isn't in top_channels.\n"
        "- Returns channel metadata including type (public/private), member count, topic, and purpose.\n"
        "For FINDING a user (action=\"find_user\"):\n"
        "- Searches the live Slack API for users matching a name.\n"
        "- Use this to look up someone's user ID, or when the user wants to find or read DMs with a specific person.\n"
        "For DM conversations:\n"
        "- When the user asks about messages WITH, FROM, or TO a specific person (especially DMs), "
        "do NOT use action=\"search\". Instead:\n"
        "  1. Use action=\"find_user\" to find the person, or action=\"top_channels\" to find a DM channel with their name.\n"
        "  2. Then use action=\"get_messages\" with the DM's channel_id to read the actual conversation.\n"
        "- DM channels appear in top_channels as type \"DM\" with the other person's display name.\n"
        "- The search action finds keyword mentions across ALL channels — it's not suitable for reading a specific DM conversation.\n"
        "When SEARCH FALLS BACK to limited mode (the tool response will tell you):\n"
        "- This means the user's Slack workspace is on a free plan and full search is unavailable.\n"
        "- Tell the user transparently that the search was limited to their most active channels.\n"
        "- Ask the user to help narrow down: which specific channels, DMs, or group messages might contain what they're looking for, "
        "and an approximate timeframe.\n"
        "- Then use get_messages with include_replies=true on the channels they suggest to search more thoroughly.\n"
        "- You can make multiple get_messages calls to check several channels the user identifies.\n"
        "IMPORTANT: Whenever you reference or quote a Slack message in your response, always include the permalink "
        "so the user can jump directly to it in Slack. Search results include permalinks — always share them. "
        "If you're summarizing a conversation from get_messages, link to the channel so the user can find the discussion."
    )

    # Inject conversation summary if present
    summary = state.get("conversation_summary")
    if summary:
        system_content += f"\n\nSummary of earlier conversation:\n{summary}"

    todo_context = state.get("todo_context")
    if todo_context:
        todo_title = todo_context.get("title", "")
        todo_id = todo_context.get("todo_id", "")
        system_content += (
            f'\n\n**Active todo context:** This conversation is about todo "{todo_title}" (ID: {todo_id}). '
            f"When the user asks to modify, update, complete, snooze, or set a due date for this task, "
            f'use the manage_todos tool with action="update" or action="complete" and todo_id="{todo_id}". '
            f"Do NOT create a new todo unless the user explicitly asks to create one."
        )
        if todo_context.get("snooze_pending"):
            system_content += (
                f"\n\nThe user clicked 'Snooze' on this todo's reminder and was asked how long to snooze. "
                f"Interpret their next message as a snooze duration and use the manage_todos tool with "
                f'action="update" and todo_id="{todo_id}" with either `snooze_minutes` or `due_at` to reschedule it.'
            )

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

    # Build mapping from tool_call_id -> tool name
    tool_call_names: dict[str, str] = {}
    for msg in messages:
        if msg.role == "assistant" and msg.tool_calls:
            for tc in msg.tool_calls:
                tool_call_names[tc.id] = tc.name

    for msg in messages:
        if msg.role == "assistant" and msg.tool_calls:
            # Skip assistant messages that contain tool calls
            continue
        elif msg.role == "tool":
            # Collect tool results labeled by tool name
            tool_name = tool_call_names.get(msg.tool_call_id or "", "tool")
            content = msg.content or "(no result)"
            tool_results.append(f"**Results from {tool_name}:**\n{content}")
        else:
            clean.append(LLMMessage(role=msg.role, content=msg.content))

    # Inject tool results into the system prompt
    if tool_results and clean and clean[0].role == "system":
        results_context = (
            "\n\n**Tool results (already retrieved for this conversation):**\n\n"
            + "\n\n---\n\n".join(tool_results)
            + "\n\nUse the above tool results to answer the user's question. "
            "If a tool returned an error or no data, report that honestly to the user — "
            "do not fabricate information."
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


async def retrieve_context_node(state: AgentState, config: RunnableConfig) -> dict[str, Any]:
    """
    Retrieve conversation context with token-aware management.

    1. Load session (get existing summary + summary_through_id)
    2. Load messages after summary point (or all if no summary)
    3. Compute token budget (threshold % of model context limit)
    4. If over budget, summarize oldest messages and update session
    5. Return context_messages, conversation_summary, and context_usage
    """
    db = config["configurable"]["db"]
    message_repo = MessageRepository(db)
    session_repo = SessionRepository(db)

    session_id = state["session_id"]
    user_message = state.get("user_message", "")

    # Load session to get existing summary
    session = await session_repo.get(session_id)
    existing_summary = session.conversation_summary if session else None
    summary_through_id = session.summary_through_id if session else None

    # Load messages: after summary point or all
    if summary_through_id:
        messages = await message_repo.get_messages_after(session_id, summary_through_id)
    else:
        messages = await message_repo.get_session_messages(session_id)

    context_messages = [
        {"role": msg.role, "content": msg.content}
        for msg in messages
    ]

    # Get model context limit and compute budget
    settings = get_settings()
    model_name = settings.default_llm
    context_limit = get_context_limit(model_name)
    threshold = settings.context_usage_threshold
    token_budget = int(context_limit * threshold)

    # Estimate tokens: system_prompt + summary + history + user_message
    # Use a rough system prompt size (the actual prompt gets built later)
    system_tokens = count_tokens(SYSTEM_PROMPT) + 500  # overhead for dynamic parts
    summary_tokens = count_tokens(existing_summary) if existing_summary else 0
    user_msg_tokens = count_tokens(user_message)
    history_tokens = sum(
        count_tokens(m["content"]) + 4  # message overhead
        for m in context_messages
    )
    total_tokens = system_tokens + summary_tokens + history_tokens + user_msg_tokens

    # If over budget, summarize older messages
    if total_tokens > token_budget and len(context_messages) > 4:
        # Keep the most recent messages, summarize the rest
        # Find a split point: keep at least 4 messages for recent context
        keep_count = max(4, len(context_messages) // 4)
        to_summarize = context_messages[:-keep_count]
        context_messages = context_messages[-keep_count:]

        # Summarize
        new_summary = await summarize_messages(
            to_summarize,
            existing_summary=existing_summary,
        )

        # Update session with new summary
        # Find the last message that was summarized
        summarized_through_idx = len(messages) - keep_count - 1
        if summarized_through_idx >= 0:
            last_summarized_msg = messages[summarized_through_idx]
            await session_repo.update(
                session,
                conversation_summary=new_summary,
                summary_through_id=last_summarized_msg.id,
            )

        existing_summary = new_summary

        # Recalculate tokens after summarization
        summary_tokens = count_tokens(new_summary)
        history_tokens = sum(
            count_tokens(m["content"]) + 4
            for m in context_messages
        )
        total_tokens = system_tokens + summary_tokens + history_tokens + user_msg_tokens

    # Compute context usage
    context_usage = {
        "tokens_used": total_tokens,
        "token_limit": context_limit,
        "percentage": round(total_tokens / context_limit * 100, 1) if context_limit > 0 else 0,
        "model": model_name,
    }

    return {
        "context_messages": context_messages,
        "conversation_summary": existing_summary,
        "context_usage": context_usage,
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

    # Emit context_usage via stream writer if in streaming mode
    streaming = config["configurable"].get("streaming", False)
    if streaming:
        context_usage = state.get("context_usage")
        if context_usage:
            writer = get_stream_writer()
            writer({"type": "context_usage", **context_usage})

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
        llm_messages = build_prompt_messages(state, tz=configurable.get("timezone"))

    tool_iteration = state.get("tool_iteration", 0)
    has_tools = tool_registry.has_tools()

    # Compute effective max iterations based on tools used so far
    effective_max = DEFAULT_MAX_TOOL_ITERATIONS
    for msg in llm_messages:
        if msg.role == "assistant" and msg.tool_calls:
            for tc in msg.tool_calls:
                tool = tool_registry.get(tc.name)
                if tool:
                    effective_max = max(effective_max, tool.max_iterations)
    effective_max = min(effective_max, ABSOLUTE_MAX_TOOL_ITERATIONS)

    is_last_iteration = tool_iteration >= effective_max - 1

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
                    "response": _sanitize_response("".join(text_parts)),
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
                    "response": _sanitize_response(response.content or ""),
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
                "response": _sanitize_response("".join(text_parts)),
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
                "response": _sanitize_response(text or ""),
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

    # Build tool context from authenticated session state (never from LLM output)
    tool_context = ToolContext(
        db=configurable["db"],
        user_id=state["user_id"],
        timezone=configurable.get("timezone"),
    )

    if streaming:
        writer = get_stream_writer()

    for tc in tool_calls:
        if streaming:
            writer({"type": "tool_use", "tool_name": tc.name, "tool_args": tc.arguments})

        tool = tool_registry.get(tc.name)
        if tool:
            logger.info(f"Executing tool '{tc.name}' with args: {tc.arguments}")
            try:
                result = await tool.execute(context=tool_context, **tc.arguments)
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


# ---------------------------------------------------------------------------
# Routing functions
# ---------------------------------------------------------------------------


def route_after_process(state: AgentState) -> str:
    """Route after process_message: error or normal path."""
    if state.get("error"):
        return "end"
    return "retrieve_context"


def route_after_llm(state: AgentState) -> str:
    """Route after llm_node: tool execution or finish."""
    if state.get("tool_calls"):
        return "tool_node"
    return "save_assistant_message"


# ---------------------------------------------------------------------------
# Legacy function kept for backward compatibility with tests
# ---------------------------------------------------------------------------


async def process_message(state: AgentState) -> dict[str, Any]:
    """
    Process the incoming user message (legacy wrapper).
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
