import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from app.core.summarize import summarize_messages


class TestSummarizeMessages:
    """Tests for summarize_messages function."""

    async def test_summarize_without_existing_summary(self):
        """Should create a new summary from messages."""
        messages = [
            {"role": "user", "content": "What is Python?"},
            {"role": "assistant", "content": "Python is a programming language."},
        ]

        mock_provider = AsyncMock()
        mock_provider.generate.return_value = "The user asked about Python. The assistant explained it's a programming language."

        with patch("app.core.summarize.get_llm_provider", return_value=mock_provider), \
             patch("app.core.summarize.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(
                context_summary_model="",
                default_llm="gemini-1.5-pro",
            )

            result = await summarize_messages(messages)

        assert "Python" in result
        mock_provider.generate.assert_called_once()
        # Check that the prompt does NOT mention extending a summary
        call_args = mock_provider.generate.call_args[0][0]
        prompt_content = call_args[1].content
        assert "Existing summary" not in prompt_content

    async def test_summarize_with_existing_summary(self):
        """Should extend an existing summary."""
        messages = [
            {"role": "user", "content": "Tell me more about Python types."},
            {"role": "assistant", "content": "Python has dynamic typing."},
        ]
        existing_summary = "The user asked about Python. The assistant explained it's a programming language."

        mock_provider = AsyncMock()
        mock_provider.generate.return_value = "The user asked about Python and its type system. Python is a dynamically typed programming language."

        with patch("app.core.summarize.get_llm_provider", return_value=mock_provider), \
             patch("app.core.summarize.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(
                context_summary_model="",
                default_llm="gemini-1.5-pro",
            )

            result = await summarize_messages(messages, existing_summary=existing_summary)

        assert "Python" in result
        mock_provider.generate.assert_called_once()
        # Check that the prompt includes the existing summary
        call_args = mock_provider.generate.call_args[0][0]
        prompt_content = call_args[1].content
        assert "Existing summary" in prompt_content

    async def test_summarize_uses_custom_model(self):
        """Should use the specified model for summarization."""
        messages = [
            {"role": "user", "content": "Hello"},
        ]

        mock_provider = AsyncMock()
        mock_provider.generate.return_value = "A greeting."

        with patch("app.core.summarize.get_llm_provider", return_value=mock_provider) as mock_get_provider, \
             patch("app.core.summarize.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(
                context_summary_model="",
                default_llm="gemini-1.5-pro",
            )

            await summarize_messages(messages, model_name="claude-3-haiku")

        mock_get_provider.assert_called_once_with("claude-3-haiku")
