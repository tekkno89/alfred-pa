import pytest

from app.core.llm import LLMMessage
from app.core.tokens import (
    MODEL_CONTEXT_WINDOWS,
    count_messages_tokens,
    count_tokens,
    get_context_limit,
)


class TestCountTokens:
    """Tests for count_tokens function."""

    def test_empty_string(self):
        assert count_tokens("") == 0

    def test_simple_text(self):
        tokens = count_tokens("Hello, world!")
        assert tokens > 0
        assert tokens < 10

    def test_longer_text(self):
        text = "The quick brown fox jumps over the lazy dog. " * 10
        tokens = count_tokens(text)
        assert tokens > 50


class TestCountMessagesTokens:
    """Tests for count_messages_tokens function."""

    def test_empty_list(self):
        assert count_messages_tokens([]) == 0

    def test_single_message(self):
        messages = [LLMMessage(role="user", content="Hello!")]
        tokens = count_messages_tokens(messages)
        # Should include content tokens + overhead
        assert tokens > count_tokens("Hello!")

    def test_multiple_messages(self):
        messages = [
            LLMMessage(role="system", content="You are an assistant."),
            LLMMessage(role="user", content="Hello!"),
            LLMMessage(role="assistant", content="Hi there!"),
        ]
        tokens = count_messages_tokens(messages)
        # Should be more than sum of content tokens
        content_only = sum(count_tokens(m.content or "") for m in messages)
        assert tokens > content_only

    def test_message_with_none_content(self):
        messages = [LLMMessage(role="assistant", content=None)]
        tokens = count_messages_tokens(messages)
        # Just overhead, no content tokens
        assert tokens == 4  # _MESSAGE_OVERHEAD


class TestGetContextLimit:
    """Tests for get_context_limit function."""

    def test_exact_match(self):
        assert get_context_limit("gemini-1.5-pro") == 1_000_000
        assert get_context_limit("claude-3.5-sonnet") == 200_000

    def test_prefix_match(self):
        # Should match "gemini-2.0-flash" prefix
        assert get_context_limit("gemini-2.0-flash-001") == 1_000_000
        # Should match "claude-3-opus" prefix
        assert get_context_limit("claude-3-opus-20240229") == 200_000

    def test_openrouter_prefix(self):
        assert get_context_limit("anthropic/claude-3.5-sonnet") == 200_000
        assert get_context_limit("google/gemini-2.0-flash") == 1_000_000

    def test_unknown_model_returns_default(self):
        assert get_context_limit("unknown-model-xyz") == MODEL_CONTEXT_WINDOWS["_default"]
        assert get_context_limit("") == MODEL_CONTEXT_WINDOWS["_default"]

    def test_longest_prefix_wins(self):
        # "anthropic/claude" matches but "claude-3.5-sonnet" would be a longer match
        # for a model like "claude-3.5-sonnet-v2"
        limit = get_context_limit("claude-3.5-sonnet-v2")
        assert limit == 200_000
