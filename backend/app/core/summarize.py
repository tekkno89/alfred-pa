"""Conversation summarization for context window management."""

import logging

from app.core.config import get_settings
from app.core.llm import LLMMessage, get_llm_provider

logger = logging.getLogger(__name__)

_SUMMARIZE_PROMPT = """\
Summarize the following conversation, preserving:
- Key facts, decisions, and conclusions
- User preferences and requests
- Important context needed for follow-up
- Any action items or commitments

Be concise but thorough. Write in third person (e.g., "The user asked about...").
"""

_EXTEND_PROMPT = """\
Below is an existing summary of an earlier part of a conversation, followed by new messages.
Extend the summary to incorporate the new messages, preserving all important information
from both the existing summary and the new messages.

Be concise but thorough. Write in third person (e.g., "The user asked about...").

Existing summary:
{existing_summary}

New messages to incorporate:
"""


async def summarize_messages(
    messages: list[dict[str, str]],
    existing_summary: str | None = None,
    model_name: str | None = None,
) -> str:
    """
    Summarize conversation messages using an LLM.

    Args:
        messages: List of {"role": ..., "content": ...} dicts to summarize.
        existing_summary: If provided, extend this summary with the new messages.
        model_name: Model to use for summarization (defaults to settings).

    Returns:
        The summary text.
    """
    settings = get_settings()
    summary_model = model_name or settings.context_summary_model or settings.default_llm
    provider = get_llm_provider(summary_model)

    # Format the messages as text
    formatted = "\n".join(
        f"{msg['role'].capitalize()}: {msg['content']}" for msg in messages
    )

    if existing_summary:
        prompt = _EXTEND_PROMPT.format(existing_summary=existing_summary) + formatted
    else:
        prompt = _SUMMARIZE_PROMPT + "\n" + formatted

    llm_messages = [
        LLMMessage(role="system", content="You are a concise conversation summarizer."),
        LLMMessage(role="user", content=prompt),
    ]

    summary = await provider.generate(llm_messages)
    return summary
