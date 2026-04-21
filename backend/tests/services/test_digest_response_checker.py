"""Tests for digest_response_checker service."""

import pytest
from datetime import datetime
from unittest.mock import AsyncMock, patch, MagicMock

from app.services.digest_response_checker import DigestResponseChecker
from app.services.digest_grouper import ConversationGroup
from app.db.models.triage import TriageClassification


def create_classification(
    channel_id: str,
    message_ts: str,
    thread_ts: str | None = None,
    user_reacted_at: datetime | None = None,
    user_responded_at: datetime | None = None,
) -> TriageClassification:
    """Helper to create a TriageClassification for testing."""
    return TriageClassification(
        id="test-id",
        user_id="test-user",
        sender_slack_id="U-sender",
        sender_name="Sender",
        channel_id=channel_id,
        channel_name="test-channel",
        message_ts=message_ts,
        thread_ts=thread_ts,
        priority_level="p1",
        confidence=0.9,
        classification_path="channel",
        created_at=datetime.utcnow(),
        user_reacted_at=user_reacted_at,
        user_responded_at=user_responded_at,
    )


def create_conversation(
    channel_id: str = "C123",
    message_tses: list[str] = None,
    thread_ts: str | None = None,
    conversation_type: str = "channel",
    has_reacted: bool = False,
    has_responded: bool = False,
) -> ConversationGroup:
    """Helper to create a ConversationGroup for testing."""
    if message_tses is None:
        message_tses = ["100.1"]

    messages = []
    for ts in message_tses:
        msg = create_classification(
            channel_id=channel_id,
            message_ts=ts,
            thread_ts=thread_ts,
            user_reacted_at=datetime.utcnow() if has_reacted else None,
            user_responded_at=datetime.utcnow() if has_responded else None,
        )
        messages.append(msg)

    return ConversationGroup(
        id=f"{conversation_type}:{channel_id}",
        messages=messages,
        conversation_type=conversation_type,
        channel_id=channel_id,
        thread_ts=thread_ts,
        participants=["U-sender"],
    )


class TestDigestResponseChecker:
    """Tests for DigestResponseChecker."""

    def test_init(self):
        """Checker initializes properly."""
        checker = DigestResponseChecker()
        assert checker.slack_service is not None

    @pytest.mark.asyncio
    async def test_filter_empty_conversations(self):
        """Empty input returns empty list."""
        checker = DigestResponseChecker()
        result = await checker.filter_unresponded_conversations("user-id", "U-user", [])
        assert result == []

    @pytest.mark.asyncio
    async def test_filter_reacted_conversation(self):
        """Conversations where user reacted are filtered out."""
        checker = DigestResponseChecker()
        conv = create_conversation(has_reacted=True)

        # Mock the Slack API to prevent real calls
        with patch.object(checker, "_check_user_message_response", return_value=False):
            result = await checker.filter_unresponded_conversations(
                "user-id", "U-user", [conv]
            )

        assert result == []

    @pytest.mark.asyncio
    async def test_filter_responded_conversation(self):
        """Conversations where user responded are filtered out."""
        checker = DigestResponseChecker()
        conv = create_conversation(has_responded=True)

        # Mock the Slack API to prevent real calls
        with patch.object(checker, "_check_user_message_response", return_value=False):
            result = await checker.filter_unresponded_conversations(
                "user-id", "U-user", [conv]
            )

        assert result == []

    @pytest.mark.asyncio
    async def test_keep_unresponded_conversation(self):
        """Unresponded conversations are kept."""
        checker = DigestResponseChecker()
        conv = create_conversation(has_reacted=False, has_responded=False)

        # Mock the Slack API to return no user messages
        with patch.object(checker, "_check_user_message_response", return_value=False):
            result = await checker.filter_unresponded_conversations(
                "user-id", "U-user", [conv]
            )

        assert len(result) == 1
        assert result[0] == conv

    @pytest.mark.asyncio
    async def test_filter_mixed_conversations(self):
        """Mix of responded and unresponded conversations."""
        checker = DigestResponseChecker()

        convs = [
            create_conversation(
                channel_id="C1", has_reacted=True
            ),  # Filtered by reaction
            create_conversation(
                channel_id="C2", has_responded=True
            ),  # Filtered by response
            create_conversation(
                channel_id="C3", has_reacted=False, has_responded=False
            ),  # Kept
        ]

        # Mock the Slack API to prevent real calls and return no user messages
        with patch.object(checker, "_check_user_message_response", return_value=False):
            result = await checker.filter_unresponded_conversations(
                "user-id", "U-user", convs
            )

        # C1 filtered by reaction, C2 filtered by response, C3 kept
        assert len(result) == 1
        assert result[0].channel_id == "C3"

    @pytest.mark.asyncio
    async def test_check_user_message_response_user_posted_after(self):
        """Detects user message posted after conversation."""
        checker = DigestResponseChecker()
        conv = create_conversation(message_tses=["100.1", "100.2"])

        mock_client = AsyncMock()
        mock_client.conversations_history = AsyncMock(
            return_value={
                "messages": [
                    {"ts": "100.3", "user": "U-user"},  # User message after
                    {"ts": "100.2", "user": "U-sender"},
                ]
            }
        )
        checker.slack_service.client = mock_client

        result = await checker._check_user_message_response("U-user", conv)

        assert result is True

    @pytest.mark.asyncio
    async def test_check_user_message_response_no_user_post(self):
        """No user message after conversation."""
        checker = DigestResponseChecker()
        conv = create_conversation(message_tses=["100.1", "100.2"])

        mock_client = AsyncMock()
        mock_client.conversations_history = AsyncMock(
            return_value={
                "messages": [
                    {"ts": "100.3", "user": "U-other"},  # Not the user
                    {"ts": "100.2", "user": "U-sender"},
                ]
            }
        )
        checker.slack_service.client = mock_client

        result = await checker._check_user_message_response("U-user", conv)

        assert result is False

    @pytest.mark.asyncio
    async def test_check_user_message_response_thread(self):
        """Checks thread replies for user response."""
        checker = DigestResponseChecker()
        conv = create_conversation(
            thread_ts="T1",
            message_tses=["100.1", "100.2"],
            conversation_type="thread",
        )

        mock_client = AsyncMock()
        mock_client.conversations_replies = AsyncMock(
            return_value={
                "messages": [
                    {"ts": "100.3", "user": "U-user"},  # User replied in thread
                ]
            }
        )
        checker.slack_service.client = mock_client

        result = await checker._check_user_message_response("U-user", conv)

        assert result is True
        mock_client.conversations_replies.assert_called_once()

    @pytest.mark.asyncio
    async def test_check_user_message_response_skips_bots(self):
        """Bot messages are not counted as user responses."""
        checker = DigestResponseChecker()
        conv = create_conversation(message_tses=["100.1"])

        mock_client = AsyncMock()
        mock_client.conversations_history = AsyncMock(
            return_value={
                "messages": [
                    {"ts": "100.2", "user": "U-user", "bot_id": "B123"},  # Bot message
                    {
                        "ts": "100.3",
                        "user": "U-user",
                        "subtype": "bot_message",
                    },  # Bot message
                ]
            }
        )
        checker.slack_service.client = mock_client

        result = await checker._check_user_message_response("U-user", conv)

        assert result is False

    @pytest.mark.asyncio
    async def test_check_user_message_response_error(self):
        """Returns False on error (conservative)."""
        checker = DigestResponseChecker()
        conv = create_conversation()

        mock_client = AsyncMock()
        mock_client.conversations_history = AsyncMock(
            side_effect=Exception("API error")
        )
        checker.slack_service.client = mock_client

        result = await checker._check_user_message_response("U-user", conv)

        assert result is False


class TestDigestResponseCheckerFilterMessages:
    """Tests for filter_unresponded_messages (non-conversation mode)."""

    @pytest.mark.asyncio
    async def test_filter_empty_messages(self):
        """Empty input returns empty list."""
        checker = DigestResponseChecker()
        result = await checker.filter_unresponded_messages("user-id", "U-user", [])
        assert result == []

    @pytest.mark.asyncio
    async def test_filter_reacted_messages(self):
        """Messages with user_reacted_at are filtered."""
        checker = DigestResponseChecker()
        messages = [
            create_classification("C1", "100.1", user_reacted_at=datetime.utcnow()),
            create_classification("C1", "100.2"),
        ]

        with patch.object(checker, "_get_user_messages_after", return_value=[]):
            result = await checker.filter_unresponded_messages(
                "user-id", "U-user", messages
            )

        assert len(result) == 1
        assert result[0].message_ts == "100.2"

    @pytest.mark.asyncio
    async def test_filter_messages_user_posted_after(self):
        """Messages user posted after are filtered."""
        checker = DigestResponseChecker()
        messages = [
            create_classification("C1", "100.1"),
            create_classification("C1", "100.2"),
            create_classification("C1", "100.3"),
        ]

        # User posted at 100.5, so 100.1, 100.2, 100.3 are before
        # But we're checking if user posted after EACH message
        with patch.object(checker, "_get_user_messages_after", return_value=["100.5"]):
            result = await checker.filter_unresponded_messages(
                "user-id", "U-user", messages
            )

        # All messages have a user post after them, so all filtered
        assert len(result) == 0

    @pytest.mark.asyncio
    async def test_filter_messages_partial(self):
        """Only some messages have user post after."""
        checker = DigestResponseChecker()
        messages = [
            create_classification("C1", "100.1"),  # User posted after (100.5 > 100.1)
            create_classification("C1", "100.6"),  # No user post after
        ]

        with patch.object(checker, "_get_user_messages_after", return_value=["100.5"]):
            result = await checker.filter_unresponded_messages(
                "user-id", "U-user", messages
            )

        assert len(result) == 1
        assert result[0].message_ts == "100.6"


class TestDigestResponseCheckerGetUserMessages:
    """Tests for _get_user_messages_after."""

    @pytest.mark.asyncio
    async def test_get_user_messages_success(self):
        """Returns user message timestamps."""
        checker = DigestResponseChecker()

        mock_client = AsyncMock()
        mock_client.conversations_history = AsyncMock(
            return_value={
                "messages": [
                    {"ts": "100.5", "user": "U-user"},
                    {"ts": "100.4", "user": "U-other"},
                    {"ts": "100.3", "user": "U-user"},
                ]
            }
        )
        checker.slack_service.client = mock_client

        result = await checker._get_user_messages_after("U-user", "C123", "100.0")

        assert result == ["100.5", "100.3"]

    @pytest.mark.asyncio
    async def test_get_user_messages_skips_bots(self):
        """Bot messages are excluded."""
        checker = DigestResponseChecker()

        mock_client = AsyncMock()
        mock_client.conversations_history = AsyncMock(
            return_value={
                "messages": [
                    {"ts": "100.5", "user": "U-user", "bot_id": "B123"},
                    {"ts": "100.4", "user": "U-user"},
                ]
            }
        )
        checker.slack_service.client = mock_client

        result = await checker._get_user_messages_after("U-user", "C123", "100.0")

        assert result == ["100.4"]

    @pytest.mark.asyncio
    async def test_get_user_messages_error(self):
        """Returns empty list on error."""
        checker = DigestResponseChecker()

        mock_client = AsyncMock()
        mock_client.conversations_history = AsyncMock(
            side_effect=Exception("API error")
        )
        checker.slack_service.client = mock_client

        result = await checker._get_user_messages_after("U-user", "C123", "100.0")

        assert result == []
