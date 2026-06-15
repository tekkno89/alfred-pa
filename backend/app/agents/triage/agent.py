"""TriageAgent — classifies a single Slack message via LangGraph."""

import logging
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.triage.graph import create_triage_graph
from app.agents.triage.state import TriageAgentState
from app.agents.triage.tools import get_triage_tool_registry

logger = logging.getLogger(__name__)


class TriageAgent:
    """Classify a Slack message by running a LangGraph agent with triage tools.

    Unlike the main Alfred agent, the triage agent:
    - Runs once per message (no conversation history, no checkpoints)
    - Does not stream responses
    - Returns a structured result dict instead of text
    """

    def __init__(self, db: AsyncSession):
        self.db = db
        self.graph = create_triage_graph()
        self.tool_registry = get_triage_tool_registry()

    async def classify(
        self,
        *,
        user_id: str,
        channel_id: str,
        message_ts: str,
        sender_slack_id: str,
        event_type: str = "message",
        thread_ts: str | None = None,
        bot_id: str | None = None,
        message_text_fallback: str = "",
        sensitivity: str = "normal",
        custom_rules: str | None = None,
        p0_definition: str | None = None,
        p1_definition: str | None = None,
        p2_definition: str | None = None,
        p3_definition: str | None = None,
        p1_max_wait_minutes: int = 30,
        p1_settled_threshold_minutes: int = 5,
        eod_review_time: str = "17:00",
    ) -> dict[str, Any]:
        """Classify a Slack message and take the appropriate action.

        Args:
            user_id: Alfred user ID who owns this triage config.
            channel_id: Slack channel where the message was posted.
            message_ts: Slack message timestamp.
            sender_slack_id: Slack user ID of the message sender.
            event_type: Slack event type (e.g. "message", "app_mention").
            thread_ts: Thread timestamp if message is in a thread.
            bot_id: Bot ID if message is from a bot.
            message_text_fallback: Fallback text from the Slack event payload.
            sensitivity: User's sensitivity preference ("low", "normal", "high").
            custom_rules: User-defined classification rules.
            p0_definition: Custom P0 priority definition.
            p1_definition: Custom P1 priority definition.
            p2_definition: Custom P2 priority definition.
            p3_definition: Custom P3 priority definition.
            p1_max_wait_minutes: Max minutes before P1 digest delivery.
            p1_settled_threshold_minutes: Minutes of inactivity before P1 is "settled".
            eod_review_time: Time for end-of-day digest (HH:MM format).

        Returns:
            Dict with keys: action_taken, classification_id, error,
            needs_review, tool_iterations, tool_call_count.
        """
        initial_state: TriageAgentState = {
            # Input
            "user_id": user_id,
            "channel_id": channel_id,
            "message_ts": message_ts,
            "thread_ts": thread_ts,
            "sender_slack_id": sender_slack_id,
            "event_type": event_type,
            "bot_id": bot_id,
            "message_text_fallback": message_text_fallback,
            # User config
            "sensitivity": sensitivity,
            "custom_rules": custom_rules,
            "p0_definition": p0_definition,
            "p1_definition": p1_definition,
            "p2_definition": p2_definition,
            "p3_definition": p3_definition,
            "p1_max_wait_minutes": p1_max_wait_minutes,
            "p1_settled_threshold_minutes": p1_settled_threshold_minutes,
            "eod_review_time": eod_review_time,
            # Agent working state (initialized by setup_node, but required by TypedDict)
            "llm_messages": [],
            "tool_calls": None,
            "tool_iteration": 0,
            "tool_call_count": 0,
            # Output
            "action_taken": None,
            "classification_id": None,
            "error": None,
            # Metadata
            "needs_review": False,
        }

        config = {
            "configurable": {
                "db": self.db,
                "user_id": user_id,
                "tool_registry": self.tool_registry,
            },
            "recursion_limit": 25,
        }

        try:
            final_state = await self.graph.ainvoke(initial_state, config)

            return {
                "action_taken": final_state.get("action_taken"),
                "classification_id": final_state.get("classification_id"),
                "error": final_state.get("error"),
                "needs_review": final_state.get("needs_review", False),
                "tool_iterations": final_state.get("tool_iteration", 0),
                "tool_call_count": final_state.get("tool_call_count", 0),
            }
        except Exception as e:
            logger.error("TriageAgent.classify failed: %s", e, exc_info=True)
            return {
                "action_taken": None,
                "classification_id": None,
                "error": f"Agent execution failed: {e}",
                "needs_review": True,
                "tool_iterations": 0,
                "tool_call_count": 0,
            }
