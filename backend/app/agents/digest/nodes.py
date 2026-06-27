"""Node functions and routing logic for the digest agent graph."""

import json
import logging
from typing import Any

from langchain_core.runnables import RunnableConfig

from app.agents.digest.prompt import MAX_TOOL_CALLS, build_digest_prompt
from app.agents.digest.state import DigestAgentState
from app.core.config import get_settings
from app.core.llm import LLMMessage, get_llm_provider
from app.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Node functions
# ---------------------------------------------------------------------------


async def setup_node(state: DigestAgentState, config: RunnableConfig) -> dict[str, Any]:
    """Build system prompt and initial user message listing message groups.

    Creates the LLM conversation with:
    1. System prompt (from build_digest_prompt with digest_type and p3_count)
    2. User message listing all message groups with their abstracts
    """
    system_prompt = build_digest_prompt(
        digest_type=state["digest_type"],
        p3_count=state.get("p3_count", 0),
    )

    groups = state.get("groups") or []

    # Build the user message with all message groups
    parts: list[str] = []
    parts.append(f"You have {len(groups)} message group(s) to compose into a digest.")
    parts.append("")

    for i, group in enumerate(groups, start=1):
        group_id = group.get("group_id", "ungrouped")
        label = f"(group_id: {group_id})" if group_id != "ungrouped" else "(ungrouped)"
        parts.append(f"Group {i} {label}:")

        messages = group.get("messages") or []
        for msg in messages:
            channel = msg.get("channel_name", "unknown")
            sender = msg.get("sender_name", "unknown")
            abstract = msg.get("abstract", "")
            permalink = msg.get("permalink", "")

            line = f'- [#{channel}] {sender}: "{abstract}"'
            if permalink:
                line += f" <{permalink}|View>"
            parts.append(line)

        parts.append("")

    parts.append(
        "Compose a digest, then call send_digest_dm, save_digest_record, and mark_delivered."
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
        "digest_sent": False,
        "digest_record_id": None,
        "error": None,
    }


async def llm_node(state: DigestAgentState, config: RunnableConfig) -> dict[str, Any]:
    """Call the LLM with tools and return its response.

    Uses generate_with_tools for non-streaming tool-calling.
    Appends the assistant response to llm_messages.
    """
    configurable = config["configurable"]
    tool_registry: ToolRegistry = configurable["tool_registry"]

    settings = get_settings()
    provider = get_llm_provider(
        settings.triage_classification_model,
        location=settings.digest_vertex_location or settings.triage_vertex_location or settings.vertex_location,
    )

    tool_defs = tool_registry.get_definitions()
    llm_messages = list(state.get("llm_messages") or [])
    tool_iteration = state.get("tool_iteration", 0)

    try:
        response = await provider.generate_with_tools(
            messages=llm_messages,
            tools=tool_defs,
            temperature=0.3,
            max_tokens=8192,
        )
    except Exception as e:
        logger.error("Digest LLM call failed: %s", e)
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


async def tool_node(state: DigestAgentState, config: RunnableConfig) -> dict[str, Any]:
    """Execute tool calls from the LLM and check for terminal actions.

    Builds a tool_context dict with db and user_id.
    Tracks tool_call_count and enforces MAX_TOOL_CALLS limit.
    Checks for digest_sent and digest_record_id from tool results.
    """
    configurable = config["configurable"]
    tool_registry: ToolRegistry = configurable["tool_registry"]
    db = configurable["db"]
    user_id = configurable["user_id"]

    tool_calls = state.get("tool_calls") or []
    llm_messages = list(state.get("llm_messages") or [])
    tool_call_count = state.get("tool_call_count", 0)

    # Build tool context dict
    tool_context = {
        "db": db,
        "user_id": user_id,
    }

    digest_sent = state.get("digest_sent", False)
    digest_record_id = state.get("digest_record_id")

    for tc in tool_calls:
        # Enforce tool call limit
        if tool_call_count >= MAX_TOOL_CALLS:
            logger.warning(
                "Digest agent hit tool call limit (%d) — returning error to LLM",
                MAX_TOOL_CALLS,
            )
            llm_messages.append(LLMMessage(
                role="tool",
                content=json.dumps({
                    "error": f"Tool call limit ({MAX_TOOL_CALLS}) reached. "
                    "You must finalize the digest now with the information you have."
                }),
                tool_call_id=tc.id,
            ))
            continue

        tool = tool_registry.get(tc.name)
        if tool:
            logger.info("Digest executing tool '%s' with args: %s", tc.name, tc.arguments)
            try:
                result = await tool.execute(context=tool_context, **tc.arguments)
                logger.info("Digest tool '%s' returned %d chars", tc.name, len(result))
            except Exception as e:
                logger.error("Digest tool '%s' execution error: %s", tc.name, e)
                result = json.dumps({"error": f"Tool error: {e}"})
        else:
            result = json.dumps({"error": f"Unknown tool: {tc.name}"})

        tool_call_count += 1

        llm_messages.append(LLMMessage(
            role="tool",
            content=result,
            tool_call_id=tc.id,
        ))

        # Check for terminal actions
        try:
            result_data = json.loads(result)
            status = result_data.get("status")

            # send_digest_dm returns {"status": "sent"}
            if tc.name == "send_digest_dm" and status == "sent":
                digest_sent = True

            # save_digest_record returns {"status": "saved", "digest_record_id": "..."}
            if tc.name == "save_digest_record" and status == "saved":
                digest_record_id = result_data.get("digest_record_id")
        except (json.JSONDecodeError, AttributeError):
            pass

    return {
        "llm_messages": llm_messages,
        "tool_calls": None,
        "tool_call_count": tool_call_count,
        "digest_sent": digest_sent,
        "digest_record_id": digest_record_id,
    }


# ---------------------------------------------------------------------------
# Routing functions
# ---------------------------------------------------------------------------


def route_after_llm(state: DigestAgentState) -> str:
    """Route after llm_node: execute tools, or end."""
    if state.get("error"):
        return "end"
    if state.get("digest_sent"):
        return "end"
    if state.get("tool_calls"):
        return "tool_node"
    # No tool calls and no digest sent — shouldn't happen, but end gracefully
    return "end"


def route_after_tool(state: DigestAgentState) -> str:
    """Route after tool_node: continue LLM loop or end."""
    # All done — digest sent and record saved
    if state.get("digest_sent") and state.get("digest_record_id"):
        return "end"
    if state.get("error"):
        return "end"
    if state.get("tool_call_count", 0) >= MAX_TOOL_CALLS:
        return "end"
    # Continue — agent may need more tool calls
    return "llm_node"
