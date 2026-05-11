"""Unit tests for SensitiveContentFetcher."""

from datetime import datetime
from unittest.mock import AsyncMock

import pytest
from slack_sdk.errors import SlackApiError

from app.services.sensitive_content_fetcher import (
    FetchedMessage,
    SensitiveContentFetcher,
)


@pytest.fixture
def mock_client():
    return AsyncMock()


@pytest.fixture
def fetcher(mock_client):
    return SensitiveContentFetcher(mock_client)


class TestFetchMessage:
    async def test_fetch_message_returns_parsed_message(self, fetcher, mock_client):
        mock_client.conversations_history.return_value = {
            "messages": [
                {
                    "ts": "123.456",
                    "user": "U123",
                    "text": "Hello world",
                }
            ]
        }

        result = await fetcher.fetch_message("C123", "123.456")

        assert result is not None
        assert result.message_ts == "123.456"
        assert result.sender_slack_id == "U123"
        assert result.text == "Hello world"
        assert result.is_bot is False

    async def test_fetch_message_returns_none_on_rate_limit(
        self, fetcher, mock_client
    ):
        error = SlackApiError(
            message="ratelimited", response={"error": "ratelimited"}
        )
        mock_client.conversations_history.side_effect = error

        result = await fetcher.fetch_message("C123", "123.456")

        assert result is None

    async def test_fetch_message_returns_none_not_found(self, fetcher, mock_client):
        mock_client.conversations_history.return_value = {"messages": []}

        result = await fetcher.fetch_message("C123", "123.456")

        assert result is None


class TestFetchThread:
    async def test_fetch_thread_returns_messages(self, fetcher, mock_client):
        mock_client.conversations_replies.return_value = {
            "messages": [
                {"ts": "123.000", "user": "U1", "text": "First"},
                {"ts": "123.001", "user": "U2", "text": "Second"},
            ]
        }

        result = await fetcher.fetch_thread("C123", "123.000")

        assert len(result) == 2
        assert result[0].text == "First"
        assert result[1].text == "Second"

    async def test_fetch_thread_returns_empty_on_error(self, fetcher, mock_client):
        error = SlackApiError(
            message="error", response={"error": "channel_not_found"}
        )
        mock_client.conversations_replies.side_effect = error

        result = await fetcher.fetch_thread("C123", "123.000")

        assert result == []


class TestFetchDmConversation:
    async def test_fetch_dm_conversation_returns_messages(
        self, fetcher, mock_client
    ):
        mock_client.conversations_history.return_value = {
            "messages": [
                {"ts": "123.001", "user": "U1", "text": "DM 1"},
                {"ts": "123.002", "user": "U2", "text": "DM 2"},
            ]
        }

        result = await fetcher.fetch_dm_conversation("D123", max_messages=20)

        assert len(result) == 2
        mock_client.conversations_history.assert_called_once_with(
            channel="D123", limit=20
        )


class TestCheckEngagement:
    async def test_check_engagement_detects_user_message(self, fetcher, mock_client):
        mock_client.conversations_history.return_value = {
            "messages": [
                {"ts": "123.010", "user": "U123", "text": "My reply"},
                {"ts": "123.005", "user": "U456", "text": "Original"},
            ]
        }

        result = await fetcher.check_engagement("C123", "U123", "123.000")

        assert result is True

    async def test_check_engagement_detects_user_reaction(
        self, fetcher, mock_client
    ):
        mock_client.conversations_history.return_value = {
            "messages": [
                {
                    "ts": "123.005",
                    "user": "U456",
                    "text": "Original",
                    "reactions": [{"name": "thumbsup", "users": ["U123"]}],
                },
            ]
        }

        result = await fetcher.check_engagement("C123", "U123", "123.000")

        assert result is True

    async def test_check_engagement_returns_false_no_engagement(
        self, fetcher, mock_client
    ):
        mock_client.conversations_history.return_value = {
            "messages": [
                {"ts": "123.005", "user": "U456", "text": "Message"},
            ]
        }

        result = await fetcher.check_engagement("C123", "U123", "123.000")

        assert result is False

    async def test_check_engagement_uses_thread_replies(self, fetcher, mock_client):
        mock_client.conversations_replies.return_value = {
            "messages": [
                {"ts": "123.010", "user": "U123", "text": "Thread reply"},
            ]
        }

        result = await fetcher.check_engagement(
            "C123", "U123", "123.000", thread_ts="123.000"
        )

        assert result is True
        mock_client.conversations_replies.assert_called_once()


class TestParseMessage:
    def test_parse_message_handles_bot_messages(self, fetcher):
        result = fetcher._parse_message(
            {
                "ts": "123.456",
                "bot_id": "B123",
                "text": "Bot message",
            }
        )

        assert result.is_bot is True
        assert result.sender_slack_id == "B123"

    def test_parse_message_parses_timestamp(self, fetcher):
        result = fetcher._parse_message(
            {
                "ts": "1700000000.123456",
                "user": "U123",
                "text": "Test",
            }
        )

        assert result.created_at is not None
        assert result.created_at.year == 2023
