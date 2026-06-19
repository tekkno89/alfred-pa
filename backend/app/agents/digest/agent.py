"""DigestAgent — composes and delivers message digests via LangGraph."""

import logging
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.digest.graph import create_digest_graph
from app.agents.digest.state import DigestAgentState
from app.agents.digest.tools import get_digest_tool_registry

logger = logging.getLogger(__name__)


class DigestAgent:
    """Compose and deliver a Slack digest by running a LangGraph agent.

    Unlike the main Alfred agent, the digest agent:
    - Runs once per digest (no conversation history, no checkpoints)
    - Does not stream responses
    - Returns a structured result dict instead of text
    """

    def __init__(self, db: AsyncSession):
        self.db = db
        self.graph = create_digest_graph()
        self.tool_registry = get_digest_tool_registry()

    async def compose_and_deliver(
        self,
        user_id: str,
        digest_type: str,  # "p1" or "eod"
        groups: list[dict[str, Any]],
        p3_count: int = 0,
    ) -> dict[str, Any]:
        """Compose and deliver a digest.

        Args:
            user_id: Alfred user ID who receives this digest.
            digest_type: Either "p1" (important/urgent) or "eod" (end of day).
            groups: List of message groups. Each group is a dict with:
                - group_id: str — group identifier (or "ungrouped")
                - messages: list[dict] — messages in the group, each with
                  id, sender_name, channel_name, abstract, permalink, etc.
            p3_count: Number of P3 (auto-ignored) messages today. Only shown
                in EOD digests as a footer note.

        Returns:
            Dict with keys: digest_sent, digest_record_id, error.
        """
        initial_state: DigestAgentState = {
            # Input
            "user_id": user_id,
            "digest_type": digest_type,
            "groups": groups,
            "p3_count": p3_count,
            # Agent working state (initialized by setup_node, but required by TypedDict)
            "llm_messages": [],
            "tool_calls": None,
            "tool_iteration": 0,
            "tool_call_count": 0,
            # Output
            "digest_sent": False,
            "digest_record_id": None,
            "error": None,
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
                "digest_sent": final_state.get("digest_sent", False),
                "digest_record_id": final_state.get("digest_record_id"),
                "error": final_state.get("error"),
            }
        except Exception as e:
            logger.exception("Digest agent graph execution failed")
            return {
                "digest_sent": False,
                "digest_record_id": None,
                "error": str(e),
            }
