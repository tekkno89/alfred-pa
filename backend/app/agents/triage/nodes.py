"""Node functions and routing logic for the triage agent graph."""

import json
import logging
from typing import Any

from langchain_core.runnables import RunnableConfig

from app.agents.triage.prompt import MAX_TOOL_CALLS, build_system_prompt
from app.agents.triage.state import TriageAgentState
from app.core.config import get_settings
from app.core.llm import LLMMessage, get_llm_provider
from app.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Node functions
# ---------------------------------------------------------------------------


async def setup_node(state: TriageAgentState, config: RunnableConfig) -> dict[str, Any]:
    """Build system prompt and initial user message.

    Creates the LLM conversation with:
    1. System prompt (from build_system_prompt with user config)
    2. User message with message reference info and instructions
    """
    system_prompt = build_system_prompt(
        sensitivity=state["sensitivity"],
        custom_rules=state.get("custom_rules"),
        p0_definition=state.get("p0_definition"),
        p1_definition=state.get("p1_definition"),
        p2_definition=state.get("p2_definition"),
        p3_definition=state.get("p3_definition"),
    )

    # Build the initial user message with message reference info
    parts = [
        f"New {state['event_type']} message to classify:",
        f"- channel_id: {state['channel_id']}",
        f"- message_ts: {state['message_ts']}",
        f"- sender_slack_id: {state['sender_slack_id']}",
    ]
    if state.get("thread_ts"):
        parts.append(f"- thread_ts: {state['thread_ts']}")

    if state.get("message_text_fallback"):
        parts.append(f"\nFallback text (may be incomplete): {state['message_text_fallback']}")

    parts.append(
        "\nCall fetch_message first to get the full message content, "
        "then call get_queued_messages to check for related queued messages."
    )

    user_message = "\n".join(parts)

    llm_messages = [
        LLMMessage(role="system", content=system_prompt),
        LLMMessage(role="user", content=user_message),
    ]

    return {
        "llm_messages": llm_messages,
        "tool_iteration": 0,
        "tool_call_count": 0,
        "tool_calls": None,
        "action_taken": None,
        "classification_id": None,
        "error": None,
        "needs_review": False,
    }


async def llm_node(state: TriageAgentState, config: RunnableConfig) -> dict[str, Any]:
    """Call the LLM with tools and return its response.

    Uses generate_with_tools for non-streaming tool-calling.
    Appends the assistant response to llm_messages.
    """
    configurable = config["configurable"]
    tool_registry: ToolRegistry = configurable["tool_registry"]

    settings = get_settings()
    provider = get_llm_provider(
        settings.triage_classification_model,
        location=settings.triage_vertex_location or settings.vertex_location,
    )

    tool_defs = tool_registry.get_definitions()
    llm_messages = list(state.get("llm_messages") or [])
    tool_iteration = state.get("tool_iteration", 0)

    try:
        response = await provider.generate_with_tools(
            messages=llm_messages,
            tools=tool_defs,
            temperature=0.1,
            max_tokens=4096,
        )
    except Exception as e:
        logger.error("Triage LLM call failed: %s", e)
        return {"error": f"LLM call failed: {e}"}

    # Append assistant message to conversation
    llm_messages.append(LLMMessage(
        role="assistant",
        content=response.content,
        tool_calls=response.tool_calls,
    ))

    return {
        "llm_messages": llm_messages,
        "tool_calls": response.tool_calls,
        "tool_iteration": tool_iteration + 1,
    }


async def tool_node(state: TriageAgentState, config: RunnableConfig) -> dict[str, Any]:
    """Execute tool calls from the LLM and check for terminal actions.

    Builds a ToolContext dict with db, user_id, and agent_state (containing
    sender info, channel info, and timing config from state).
    Tracks tool_call_count and enforces MAX_TOOL_CALLS limit.
    """
    configurable = config["configurable"]
    tool_registry: ToolRegistry = configurable["tool_registry"]
    db = configurable["db"]
    user_id = configurable["user_id"]

    tool_calls = state.get("tool_calls") or []
    llm_messages = list(state.get("llm_messages") or [])
    tool_call_count = state.get("tool_call_count", 0)

    # Build agent_state dict for tools that need triage context
    agent_state: dict[str, Any] = {
        "sender_slack_id": state["sender_slack_id"],
        "channel_id": state["channel_id"],
        "message_ts": state["message_ts"],
        "thread_ts": state.get("thread_ts"),
        "bot_id": state.get("bot_id"),
        "p1_max_wait_minutes": state.get("p1_max_wait_minutes", 30),
        "p1_settled_threshold_minutes": state.get("p1_settled_threshold_minutes", 5),
        "eod_review_time": state.get("eod_review_time", "17:00"),
    }

    # Build tool context dict
    tool_context = {
        "db": db,
        "user_id": user_id,
        "agent_state": agent_state,
    }

    action_taken = state.get("action_taken")
    classification_id = state.get("classification_id")
    needs_review = state.get("needs_review", False)

    for tc in tool_calls:
        # Enforce tool call limit
        if tool_call_count >= MAX_TOOL_CALLS:
            logger.warning(
                "Triage agent hit tool call limit (%d) — returning error to LLM",
                MAX_TOOL_CALLS,
            )
            llm_messages.append(LLMMessage(
                role="tool",
                content=json.dumps({
                    "error": f"Tool call limit ({MAX_TOOL_CALLS}) reached. "
                    "You must make a classification decision now with the "
                    "information you have, or call mark_needs_review."
                }),
                tool_call_id=tc.id,
            ))
            needs_review = True
            continue

        tool = tool_registry.get(tc.name)
        if tool:
            logger.info("Triage executing tool '%s' with args: %s", tc.name, tc.arguments)
            try:
                result = await tool.execute(context=tool_context, **tc.arguments)
                logger.info("Triage tool '%s' returned %d chars", tc.name, len(result))
            except Exception as e:
                logger.error("Triage tool '%s' execution error: %s", tc.name, e)
                result = json.dumps({"error": f"Tool error: {e}"})
        else:
            result = json.dumps({"error": f"Unknown tool: {tc.name}"})

        tool_call_count += 1

        llm_messages.append(LLMMessage(
            role="tool",
            content=result,
            tool_call_id=tc.id,
        ))

        # Check if a terminal action was taken
        try:
            result_data = json.loads(result)
            status = result_data.get("status")
            if status in ("alerted", "queued"):
                action_taken = status
                classification_id = result_data.get("classification_id")
        except (json.JSONDecodeError, AttributeError):
            pass

    return {
        "llm_messages": llm_messages,
        "tool_calls": None,
        "tool_call_count": tool_call_count,
        "action_taken": action_taken,
        "classification_id": classification_id,
        "needs_review": needs_review,
    }


# ---------------------------------------------------------------------------
# Routing functions
# ---------------------------------------------------------------------------


def route_after_llm(state: TriageAgentState) -> str:
    """Route after llm_node: execute tools, or end."""
    if state.get("error"):
        return "end"
    if state.get("action_taken"):
        return "end"
    if state.get("tool_calls"):
        return "tool_node"
    # No tool calls and no action — shouldn't happen, but end gracefully
    return "end"


def route_after_tool(state: TriageAgentState) -> str:
    """Route after tool_node: continue LLM loop or end."""
    if state.get("action_taken"):
        return "end"
    if state.get("needs_review"):
        return "end"
    return "llm_node"
