"""Token counting and model context window management."""

import tiktoken

from app.core.llm import LLMMessage

# Model context window sizes (tokens)
MODEL_CONTEXT_WINDOWS: dict[str, int] = {
    # Gemini models
    "gemini-1.5-pro": 1_000_000,
    "gemini-1.5-flash": 1_000_000,
    "gemini-2.0-flash": 1_000_000,
    "gemini-2.5-flash": 1_000_000,
    "gemini-2.5-pro": 1_000_000,
    # Claude models
    "claude-3.5-sonnet": 200_000,
    "claude-3-5-sonnet": 200_000,
    "claude-3-opus": 200_000,
    "claude-3-haiku": 200_000,
    "claude-sonnet-4": 200_000,
    "claude-opus-4": 200_000,
    # OpenRouter prefixed variants
    "anthropic/claude": 200_000,
    "google/gemini": 1_000_000,
    # Fallback
    "_default": 128_000,
}

# Overhead tokens per message (role marker, formatting)
_MESSAGE_OVERHEAD = 4

# Reuse a single encoding instance
_encoding = tiktoken.get_encoding("cl100k_base")


def count_tokens(text: str) -> int:
    """Count the number of tokens in a text string."""
    return len(_encoding.encode(text))


def count_messages_tokens(messages: list[LLMMessage]) -> int:
    """Count total tokens across a list of LLM messages, including role overhead."""
    total = 0
    for msg in messages:
        total += _MESSAGE_OVERHEAD
        if msg.content:
            total += count_tokens(msg.content)
    return total


def get_context_limit(model_name: str) -> int:
    """Get the context window size for a model, using prefix matching."""
    # Exact match first
    if model_name in MODEL_CONTEXT_WINDOWS:
        return MODEL_CONTEXT_WINDOWS[model_name]

    # Prefix match (longest prefix wins)
    best_match = ""
    for prefix in MODEL_CONTEXT_WINDOWS:
        if prefix == "_default":
            continue
        if model_name.startswith(prefix) and len(prefix) > len(best_match):
            best_match = prefix

    if best_match:
        return MODEL_CONTEXT_WINDOWS[best_match]

    return MODEL_CONTEXT_WINDOWS["_default"]
