"""State schema for the digest subagent."""

from typing import Any, TypedDict

from app.core.llm import LLMMessage


class DigestGroup(TypedDict):
    """A group of related messages to include in the digest."""

    group_id: str
    messages: list[dict[str, Any]]


class DigestAgentState(TypedDict):
    """State for the digest subagent graph."""

    # Input
    user_id: str
    digest_type: str  # "p1" or "eod"
    groups: list[DigestGroup]
    p3_count: int

    # Agent working state
    llm_messages: list[LLMMessage]
    tool_calls: list | None
    tool_iteration: int
    tool_call_count: int

    # Output
    digest_sent: bool
    digest_record_id: str | None
    error: str | None
