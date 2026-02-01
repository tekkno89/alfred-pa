from typing import TypedDict, Annotated
from collections.abc import Sequence

from langgraph.graph.message import add_messages


class AgentState(TypedDict):
    """State for the Alfred agent graph."""

    # Session information
    session_id: str
    user_id: str

    # User input
    user_message: str

    # Context from history and memories
    context_messages: list[dict[str, str]]
    memories: list[str]

    # LLM response
    response: str
    response_chunks: Annotated[list[str], lambda x, y: x + y]

    # Generated message IDs
    user_message_id: str
    assistant_message_id: str

    # Error handling
    error: str | None
