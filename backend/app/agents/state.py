from typing import TypedDict


class AgentState(TypedDict):
    """State for the Alfred agent graph."""

    # Session information
    session_id: str
    user_id: str

    # User input
    user_message: str

    # Remember command detection
    is_remember_command: bool
    remember_content: str | None

    # Context from history and memories
    context_messages: list[dict[str, str]]
    memories: list[str]

    # LLM response
    response: str

    # ReAct loop state
    llm_messages: list  # LLMMessage list for the ReAct loop conversation
    tool_calls: list | None  # Current tool calls from LLM (None = no calls)
    tool_iteration: int  # Counter for ReAct iterations

    # Tool results metadata for persisting with assistant message
    tool_results_metadata: list[dict] | None

    # Generated message IDs
    user_message_id: str
    assistant_message_id: str

    # Error handling
    error: str | None
