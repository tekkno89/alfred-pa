"""Tests for SlackService."""

import hashlib
import hmac
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from slack_sdk.errors import SlackApiError

from app.services.slack import SlackService


@pytest.fixture
def slack_service():
    """Create SlackService with mocked client."""
    with patch("app.services.slack.get_settings") as mock_settings:
        mock_settings.return_value.slack_bot_token = "xoxb-test-token"
        mock_settings.return_value.slack_signing_secret = "test-signing-secret"
        service = SlackService()
        service.client = AsyncMock()
        return service


class TestVerifySignature:
    """Tests for verify_signature method."""

    async def test_valid_signature(self, slack_service):
        """Test with valid signature."""
        body = b'{"test": "data"}'
        timestamp = str(int(time.time()))

        # Compute valid signature
        sig_basestring = f"v0:{timestamp}:{body.decode('utf-8')}"
        signature = (
            "v0="
            + hmac.new(
                b"test-signing-secret",
                sig_basestring.encode("utf-8"),
                hashlib.sha256,
            ).hexdigest()
        )

        result = await slack_service.verify_signature(body, timestamp, signature)
        assert result is True

    async def test_invalid_signature(self, slack_service):
        """Test with invalid signature."""
        body = b'{"test": "data"}'
        timestamp = str(int(time.time()))
        signature = "v0=invalid_signature"

        result = await slack_service.verify_signature(body, timestamp, signature)
        assert result is False

    async def test_old_timestamp(self, slack_service):
        """Test with timestamp older than 5 minutes."""
        body = b'{"test": "data"}'
        timestamp = str(int(time.time()) - 400)  # 6+ minutes ago
        signature = "v0=any"

        result = await slack_service.verify_signature(body, timestamp, signature)
        assert result is False

    async def test_invalid_timestamp(self, slack_service):
        """Test with non-numeric timestamp."""
        body = b'{"test": "data"}'
        timestamp = "not-a-number"
        signature = "v0=any"

        result = await slack_service.verify_signature(body, timestamp, signature)
        assert result is False

    async def test_no_signing_secret(self):
        """Test without signing secret configured."""
        with patch("app.services.slack.get_settings") as mock_settings:
            mock_settings.return_value.slack_bot_token = "test"
            mock_settings.return_value.slack_signing_secret = ""
            service = SlackService()

            result = await service.verify_signature(b"test", "123", "v0=sig")
            assert result is False


class TestSendMessage:
    """Tests for send_message method."""

    async def test_send_message(self, slack_service):
        """Test sending a message to a channel."""
        slack_service.client.chat_postMessage = AsyncMock(
            return_value=MagicMock(data={"ok": True, "ts": "1234567890.123456"})
        )

        result = await slack_service.send_message(
            channel="C123456",
            text="Hello, world!",
        )

        slack_service.client.chat_postMessage.assert_called_once_with(
            channel="C123456",
            text="Hello, world!",
            thread_ts=None,
        )
        assert result["ok"] is True

    async def test_send_message_in_thread(self, slack_service):
        """Test sending a message to a thread."""
        slack_service.client.chat_postMessage = AsyncMock(
            return_value=MagicMock(data={"ok": True})
        )

        await slack_service.send_message(
            channel="C123456",
            text="Reply in thread",
            thread_ts="1234567890.123456",
        )

        slack_service.client.chat_postMessage.assert_called_once_with(
            channel="C123456",
            text="Reply in thread",
            thread_ts="1234567890.123456",
        )


class TestAddReaction:
    """Tests for add_reaction method."""

    async def test_add_reaction_success(self, slack_service):
        """Test successfully adding a reaction."""
        slack_service.client.reactions_add = AsyncMock()

        result = await slack_service.add_reaction("C123", "1234567890.123456")

        slack_service.client.reactions_add.assert_called_once_with(
            channel="C123", timestamp="1234567890.123456", name="thinking_face"
        )
        assert result is True

    async def test_add_reaction_already_reacted(self, slack_service):
        """Test adding a reaction that already exists returns True."""
        error_response = MagicMock()
        error_response.get.return_value = "already_reacted"
        slack_service.client.reactions_add = AsyncMock(
            side_effect=SlackApiError("already_reacted", error_response)
        )

        result = await slack_service.add_reaction("C123", "1234567890.123456")
        assert result is True

    async def test_add_reaction_missing_scope(self, slack_service):
        """Test adding a reaction without required scope returns False."""
        error_response = MagicMock()
        error_response.get.return_value = "missing_scope"
        slack_service.client.reactions_add = AsyncMock(
            side_effect=SlackApiError("missing_scope", error_response)
        )

        result = await slack_service.add_reaction("C123", "1234567890.123456")
        assert result is False

    async def test_add_reaction_custom_name(self, slack_service):
        """Test adding a reaction with a custom emoji name."""
        slack_service.client.reactions_add = AsyncMock()

        result = await slack_service.add_reaction("C123", "1234567890.123456", name="eyes")

        slack_service.client.reactions_add.assert_called_once_with(
            channel="C123", timestamp="1234567890.123456", name="eyes"
        )
        assert result is True


class TestRemoveReaction:
    """Tests for remove_reaction method."""

    async def test_remove_reaction_success(self, slack_service):
        """Test successfully removing a reaction."""
        slack_service.client.reactions_remove = AsyncMock()

        result = await slack_service.remove_reaction("C123", "1234567890.123456")

        slack_service.client.reactions_remove.assert_called_once_with(
            channel="C123", timestamp="1234567890.123456", name="thinking_face"
        )
        assert result is True

    async def test_remove_reaction_no_reaction(self, slack_service):
        """Test removing a reaction that doesn't exist returns True."""
        error_response = MagicMock()
        error_response.get.return_value = "no_reaction"
        slack_service.client.reactions_remove = AsyncMock(
            side_effect=SlackApiError("no_reaction", error_response)
        )

        result = await slack_service.remove_reaction("C123", "1234567890.123456")
        assert result is True

    async def test_remove_reaction_failure(self, slack_service):
        """Test removing a reaction with other error returns False."""
        error_response = MagicMock()
        error_response.get.return_value = "channel_not_found"
        slack_service.client.reactions_remove = AsyncMock(
            side_effect=SlackApiError("channel_not_found", error_response)
        )

        result = await slack_service.remove_reaction("C123", "1234567890.123456")
        assert result is False


class TestGetUserInfo:
    """Tests for get_user_info method."""

    async def test_get_user_info(self, slack_service):
        """Test getting user info."""
        slack_service.client.users_info = AsyncMock(
            return_value=MagicMock(
                data={
                    "ok": True,
                    "user": {
                        "id": "U123456",
                        "name": "testuser",
                        "real_name": "Test User",
                    },
                }
            )
        )

        result = await slack_service.get_user_info("U123456")

        slack_service.client.users_info.assert_called_once_with(user="U123456")
        assert result["id"] == "U123456"
        assert result["name"] == "testuser"
