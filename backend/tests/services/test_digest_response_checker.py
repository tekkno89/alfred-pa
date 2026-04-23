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
    )


def create_conversation(
    channel_id: str = "C123",
    message_tses: list[str] = None,
    thread_ts: str | None = None,
    conversation_type: str = "channel",
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


@pytest.fixture
def mock_db():
    """Create a mock database session."""
    return MagicMock()


class TestDigestResponseChecker:
    """Tests for DigestResponseChecker."""

    def test_init(self, mock_db):
        """Checker initializes properly."""
        checker = DigestResponseChecker(mock_db)
        assert checker.db == mock_db
        assert checker._user_clients == {}

    @pytest.mark.asyncio
    async def test_filter_empty_conversations(self, mock_db):
        """Empty input returns empty list."""
        checker = DigestResponseChecker(mock_db)
        result = await checker.filter_unresponded_conversations("user-id", "U-user", [])
        assert result == []

    @pytest.mark.asyncio
    async def test_filter_conversation_user_posted_after(self, mock_db):
        """Conversations where user posted after are filtered out."""
        checker = DigestResponseChecker(mock_db)
        conv = create_conversation()

        with patch.object(checker, "_check_user_message_response", return_value=True):
            result = await checker.filter_unresponded_conversations(
                "user-id", "U-user", [conv]
            )

        assert result == []

    @pytest.mark.asyncio
    async def test_keep_unresponded_conversation(self, mock_db):
        """Unresponded conversations are kept."""
        checker = DigestResponseChecker(mock_db)
        conv = create_conversation()

        with patch.object(checker, "_check_user_message_response", return_value=False):
            result = await checker.filter_unresponded_conversations(
                "user-id", "U-user", [conv]
            )

        assert len(result) == 1
        assert result[0] == conv

    @pytest.mark.asyncio
    async def test_filter_mixed_conversations(self, mock_db):
        """Mix of responded and unresponded conversations."""
        checker = DigestResponseChecker(mock_db)

        convs = [
            create_conversation(channel_id="C1"),
            create_conversation(channel_id="C2"),
            create_conversation(channel_id="C3"),
        ]

        async def mock_check(user_id, user_slack_id, conv):
            return conv.channel_id == "C1"

        with patch.object(
            checker, "_check_user_message_response", side_effect=mock_check
        ):
            result = await checker.filter_unresponded_conversations(
                "user-id", "U-user", convs
            )

        assert len(result) == 2
        assert {c.channel_id for c in result} == {"C2", "C3"}

    @pytest.mark.asyncio
    async def test_check_user_message_response_user_posted_after(self, mock_db):
        """Detects user message posted after conversation."""
        checker = DigestResponseChecker(mock_db)
        conv = create_conversation(message_tses=["100.1", "100.2"])

        mock_client = AsyncMock()
        mock_client.conversations_history = AsyncMock(
            return_value={
                "messages": [
                    {"ts": "100.3", "user": "U-user"},
                    {"ts": "100.2", "user": "U-sender"},
                ]
            }
        )

        with patch.object(checker, "_get_user_client", return_value=mock_client):
            result = await checker._check_user_message_response(
                "user-id", "U-user", conv
            )

        assert result is True

    @pytest.mark.asyncio
    async def test_check_user_message_response_no_user_post(self, mock_db):
        """No user message after conversation."""
        checker = DigestResponseChecker(mock_db)
        conv = create_conversation(message_tses=["100.1", "100.2"])

        mock_client = AsyncMock()
        mock_client.conversations_history = AsyncMock(
            return_value={
                "messages": [
                    {"ts": "100.3", "user": "U-other"},
                    {"ts": "100.2", "user": "U-sender"},
                ]
            }
        )

        with patch.object(checker, "_get_user_client", return_value=mock_client):
            result = await checker._check_user_message_response(
                "user-id", "U-user", conv
            )

        assert result is False

    @pytest.mark.asyncio
    async def test_check_user_message_response_thread(self, mock_db):
        """Checks thread replies for user response."""
        checker = DigestResponseChecker(mock_db)
        conv = create_conversation(
            thread_ts="T1",
            message_tses=["100.1", "100.2"],
            conversation_type="thread",
        )

        mock_client = AsyncMock()
        mock_client.conversations_replies = AsyncMock(
            return_value={
                "messages": [
                    {"ts": "100.3", "user": "U-user"},
                ]
            }
        )

        with patch.object(checker, "_get_user_client", return_value=mock_client):
            result = await checker._check_user_message_response(
                "user-id", "U-user", conv
            )

        assert result is True
        mock_client.conversations_replies.assert_called_once()

    @pytest.mark.asyncio
    async def test_check_user_message_response_skips_bots(self, mock_db):
        """Bot messages are not counted as user responses."""
        checker = DigestResponseChecker(mock_db)
        conv = create_conversation(message_tses=["100.1"])

        mock_client = AsyncMock()
        mock_client.conversations_history = AsyncMock(
            return_value={
                "messages": [
                    {"ts": "100.2", "user": "U-user", "bot_id": "B123"},
                    {"ts": "100.3", "user": "U-user", "subtype": "bot_message"},
                ]
            }
        )

        with patch.object(checker, "_get_user_client", return_value=mock_client):
            result = await checker._check_user_message_response(
                "user-id", "U-user", conv
            )

        assert result is False

    @pytest.mark.asyncio
    async def test_check_user_message_response_error(self, mock_db):
        """Returns False on error (conservative)."""
        checker = DigestResponseChecker(mock_db)
        conv = create_conversation()

        mock_client = AsyncMock()
        mock_client.conversations_history = AsyncMock(
            side_effect=Exception("API error")
        )

        with patch.object(checker, "_get_user_client", return_value=mock_client):
            result = await checker._check_user_message_response(
                "user-id", "U-user", conv
            )

        assert result is False

    @pytest.mark.asyncio
    async def test_check_user_message_response_no_client(self, mock_db):
        """Returns False when user client is unavailable."""
        checker = DigestResponseChecker(mock_db)
        conv = create_conversation()

        with patch.object(checker, "_get_user_client", return_value=None):
            result = await checker._check_user_message_response(
                "user-id", "U-user", conv
            )

        assert result is False


class TestDigestResponseCheckerFilterMessages:
    """Tests for filter_unresponded_messages (non-conversation mode)."""

    @pytest.mark.asyncio
    async def test_filter_empty_messages(self, mock_db):
        """Empty input returns empty list."""
        checker = DigestResponseChecker(mock_db)
        result = await checker.filter_unresponded_messages("user-id", "U-user", [])
        assert result == []

    @pytest.mark.asyncio
    async def test_filter_messages_user_posted_after(self, mock_db):
        """Messages user posted after are filtered."""
        checker = DigestResponseChecker(mock_db)
        messages = [
            create_classification("C1", "100.1"),
            create_classification("C1", "100.2"),
            create_classification("C1", "100.3"),
        ]

        with patch.object(checker, "_get_user_messages_after", return_value=["100.5"]):
            result = await checker.filter_unresponded_messages(
                "user-id", "U-user", messages
            )

        assert len(result) == 0

    @pytest.mark.asyncio
    async def test_filter_messages_partial(self, mock_db):
        """Only some messages have user post after."""
        checker = DigestResponseChecker(mock_db)
        messages = [
            create_classification("C1", "100.1"),
            create_classification("C1", "100.6"),
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
    async def test_get_user_messages_success(self, mock_db):
        """Returns user message timestamps."""
        checker = DigestResponseChecker(mock_db)

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

        with patch.object(checker, "_get_user_client", return_value=mock_client):
            result = await checker._get_user_messages_after(
                "user-id", "U-user", "C123", "100.0"
            )

        assert result == ["100.5", "100.3"]

    @pytest.mark.asyncio
    async def test_get_user_messages_skips_bots(self, mock_db):
        """Bot messages are excluded."""
        checker = DigestResponseChecker(mock_db)

        mock_client = AsyncMock()
        mock_client.conversations_history = AsyncMock(
            return_value={
                "messages": [
                    {"ts": "100.5", "user": "U-user", "bot_id": "B123"},
                    {"ts": "100.4", "user": "U-user"},
                ]
            }
        )

        with patch.object(checker, "_get_user_client", return_value=mock_client):
            result = await checker._get_user_messages_after(
                "user-id", "U-user", "C123", "100.0"
            )

        assert result == ["100.4"]

    @pytest.mark.asyncio
    async def test_get_user_messages_error(self, mock_db):
        """Returns empty list on error."""
        checker = DigestResponseChecker(mock_db)

        mock_client = AsyncMock()
        mock_client.conversations_history = AsyncMock(
            side_effect=Exception("API error")
        )

        with patch.object(checker, "_get_user_client", return_value=mock_client):
            result = await checker._get_user_messages_after(
                "user-id", "U-user", "C123", "100.0"
            )

        assert result == []

    @pytest.mark.asyncio
    async def test_get_user_messages_no_client(self, mock_db):
        """Returns empty list when no user client."""
        checker = DigestResponseChecker(mock_db)

        with patch.object(checker, "_get_user_client", return_value=None):
            result = await checker._get_user_messages_after(
                "user-id", "U-user", "C123", "100.0"
            )

        assert result == []


class TestGetUserClient:
    """Tests for _get_user_client caching and token lookup."""

    @pytest.mark.asyncio
    async def test_get_user_client_caches_result(self, mock_db):
        """Client is cached after first lookup."""
        checker = DigestResponseChecker(mock_db)

        mock_token = MagicMock()
        mock_repo = MagicMock()
        mock_repo.get_by_user_and_provider = AsyncMock(return_value=mock_token)
        checker.token_repo = mock_repo

        mock_encryption = MagicMock()
        mock_encryption.get_decrypted_access_token = AsyncMock(return_value="xoxp-test")
        checker.token_encryption = mock_encryption

        client1 = await checker._get_user_client("user-1")
        client2 = await checker._get_user_client("user-1")

        assert client1 is client2
        mock_repo.get_by_user_and_provider.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_user_client_no_token(self, mock_db):
        """Returns None when user has no Slack token."""
        checker = DigestResponseChecker(mock_db)

        mock_repo = MagicMock()
        mock_repo.get_by_user_and_provider = AsyncMock(return_value=None)
        checker.token_repo = mock_repo

        result = await checker._get_user_client("user-1")

        assert result is None
