"""State schema for the triage agent."""

from typing import TypedDict

from app.core.llm import LLMMessage


class TriageAgentState(TypedDict):
    """State for the triage agent graph."""

    # Input (set once at start)
    user_id: str
    channel_id: str
    message_ts: str
    thread_ts: str | None
    sender_slack_id: str
    event_type: str
    bot_id: str | None
    message_text_fallback: str

    # User config (set once at start)
    sensitivity: str
    custom_rules: str | None
    p0_definition: str | None
    p1_definition: str | None
    p2_definition: str | None
    p3_definition: str | None
    p1_max_wait_minutes: int
    p1_settled_threshold_minutes: int
    eod_review_time: str

    # Agent working state
    llm_messages: list[LLMMessage]
    tool_calls: list | None
    tool_iteration: int
    tool_call_count: int

    # Output
    action_taken: str | None
    classification_id: str | None
    error: str | None

    # Metadata
    needs_review: bool
