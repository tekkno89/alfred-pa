"""Digest subagent tools."""

from app.agents.digest.tools.fetch_channel_history import DigestFetchChannelHistoryTool
from app.agents.digest.tools.fetch_thread import DigestFetchThreadTool
from app.agents.digest.tools.mark_delivered import MarkDeliveredTool
from app.agents.digest.tools.save_digest_record import SaveDigestRecordTool
from app.agents.digest.tools.send_digest_dm import SendDigestDmTool
from app.tools.registry import ToolRegistry


def get_digest_tool_registry() -> ToolRegistry:
    """Create a ToolRegistry with all digest subagent tools."""
    registry = ToolRegistry()
    registry.register(DigestFetchThreadTool())
    registry.register(DigestFetchChannelHistoryTool())
    registry.register(SendDigestDmTool())
    registry.register(SaveDigestRecordTool())
    registry.register(MarkDeliveredTool())
    return registry


__all__ = [
    "DigestFetchChannelHistoryTool",
    "DigestFetchThreadTool",
    "MarkDeliveredTool",
    "SaveDigestRecordTool",
    "SendDigestDmTool",
    "get_digest_tool_registry",
]
