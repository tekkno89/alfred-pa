"""Triage agent tools — context-gathering and action tools."""

from app.agents.triage.tools.fetch_channel_history import FetchChannelHistoryTool
from app.agents.triage.tools.fetch_message import FetchMessageTool
from app.agents.triage.tools.fetch_thread import FetchThreadTool
from app.agents.triage.tools.get_queued_messages import GetQueuedMessagesTool
from app.agents.triage.tools.get_user_channel_rules import GetUserChannelRulesTool
from app.tools.registry import ToolRegistry


def get_triage_tool_registry() -> ToolRegistry:
    """Create a ToolRegistry with all triage agent tools."""
    registry = ToolRegistry()

    # Context-gathering tools
    registry.register(FetchMessageTool())
    registry.register(FetchThreadTool())
    registry.register(FetchChannelHistoryTool())
    registry.register(GetQueuedMessagesTool())
    registry.register(GetUserChannelRulesTool())

    # Action tools will be added in Task 3

    return registry


__all__ = [
    "FetchChannelHistoryTool",
    "FetchMessageTool",
    "FetchThreadTool",
    "GetQueuedMessagesTool",
    "GetUserChannelRulesTool",
    "get_triage_tool_registry",
]
