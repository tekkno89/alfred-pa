from typing import TypedDict


class AgentState(TypedDict):
    """State for the Alfred agent graph."""

    # Session information
    session_id: str
    user_id: str

    # User input
    user_message: str

    # Context from history
    context_messages: list[dict[str, str]]
    conversation_summary: str | None

    # Context window usage metrics
    context_usage: dict | None

    # LLM response
    response: str

    # ReAct loop state
    llm_messages: list  # LLMMessage list for the ReAct loop conversation
    tool_calls: list | None  # Current tool calls from LLM (None = no calls)
    tool_iteration: int  # Counter for ReAct iterations

    # Tool results metadata for persisting with assistant message
    tool_results_metadata: list[dict] | None

    # Thread-specific todo context (injected from Slack thread → todo mapping)
    todo_context: dict | None

    # Active coding job context (injected when session has an active coding job)
    coding_job_context: dict | None

    # Generated message IDs
    user_message_id: str
    assistant_message_id: str

    # Error handling
    error: str | None
