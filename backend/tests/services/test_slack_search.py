"""Tests for SlackSearchService."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from slack_sdk.errors import SlackApiError

from app.services.slack_search import SlackSearchService


@pytest.fixture
def mock_db():
    return AsyncMock()


@pytest.fixture
def service(mock_db):
    """Create SlackSearchService with mocked dependencies."""
    svc = SlackSearchService(mock_db)
    svc.token_repo = AsyncMock()
    svc.token_encryption = AsyncMock()
    svc.participation_repo = AsyncMock()
    svc.summary_repo = AsyncMock()
    return svc


def _make_mock_client():
    """Create a mock Slack AsyncWebClient."""
    client = AsyncMock()
    return client


def _make_token():
    """Create a mock OAuth token record."""
    token = MagicMock()
    token.user_id = "user-1"
    token.provider = "slack"
    return token


class TestSearchMessages:
    """Tests for search_messages()."""

    async def test_no_token_returns_error(self, service):
        """Should return error when user has no Slack token."""
        service.token_repo.get_by_user_and_provider.return_value = None

        result = await service.search_messages("user-1", "test query")

        assert result["error"] == "no_token"
        assert result["results"] == []

    async def test_scope_frequent_applies_channel_filters(self, service):
        """Scope='frequent' should add channel filters to the query."""
        token = _make_token()
        service.token_repo.get_by_user_and_provider.return_value = token
        service.token_encryption.get_decrypted_access_token.return_value = "xoxp-test"

        # Mock participation data
        ch1 = MagicMock()
        ch1.channel_id = "C001"
        ch1.channel_name = "general"
        service.participation_repo.get_by_user.return_value = [ch1]

        mock_response = {
            "messages": {
                "matches": [
                    {
                        "channel": {"id": "C001", "name": "general"},
                        "username": "alice",
                        "text": "test message",
                        "ts": "1700000000.000000",
                        "permalink": "https://slack.com/archives/C001/p1700000000000000",
                    }
                ],
                "total": 1,
            }
        }

        with patch("app.services.slack_search.AsyncWebClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.search_messages.return_value = mock_response
            MockClient.return_value = mock_client

            result = await service.search_messages("user-1", "test", scope="frequent")

        assert len(result["results"]) == 1
        assert result["results"][0]["channel_name"] == "general"
        assert result["results"][0]["sender_name"] == "alice"
        assert result["scope"] == "frequent"
        assert "C001" in result["scope_channels"]

    async def test_scope_all_no_channel_filter(self, service):
        """Scope='all' should not add channel filters."""
        token = _make_token()
        service.token_repo.get_by_user_and_provider.return_value = token
        service.token_encryption.get_decrypted_access_token.return_value = "xoxp-test"

        mock_response = {"messages": {"matches": [], "total": 0}}

        with patch("app.services.slack_search.AsyncWebClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.search_messages.return_value = mock_response
            MockClient.return_value = mock_client

            result = await service.search_messages("user-1", "test", scope="all")

        assert result["scope"] == "all"
        assert result["scope_channels"] == []

    async def test_missing_scope_error(self, service):
        """Should handle missing_scope error gracefully."""
        token = _make_token()
        service.token_repo.get_by_user_and_provider.return_value = token
        service.token_encryption.get_decrypted_access_token.return_value = "xoxp-test"

        mock_response = MagicMock()
        mock_response.__getitem__ = lambda self, key: {"error": "missing_scope"}.get(key)
        mock_response.get = lambda key, default=None: {"error": "missing_scope"}.get(key, default)

        with patch("app.services.slack_search.AsyncWebClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.search_messages.side_effect = SlackApiError(
                message="missing_scope", response=mock_response
            )
            MockClient.return_value = mock_client

            result = await service.search_messages("user-1", "test")

        assert result["error"] == "missing_scope"
        assert "re-authorize" in result.get("message", "").lower()

    async def test_paid_only_error(self, service):
        """Should handle paid_only error gracefully."""
        token = _make_token()
        service.token_repo.get_by_user_and_provider.return_value = token
        service.token_encryption.get_decrypted_access_token.return_value = "xoxp-test"

        mock_response = MagicMock()
        mock_response.__getitem__ = lambda self, key: {"error": "paid_only"}.get(key)
        mock_response.get = lambda key, default=None: {"error": "paid_only"}.get(key, default)

        with patch("app.services.slack_search.AsyncWebClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.search_messages.side_effect = SlackApiError(
                message="paid_only", response=mock_response
            )
            MockClient.return_value = mock_client

            result = await service.search_messages("user-1", "test")

        assert result["error"] == "paid_only"


class TestSearchHistoryFallback:
    """Tests for search_history_fallback()."""

    async def test_no_token(self, service):
        """Should return error when no token."""
        service.token_repo.get_by_user_and_provider.return_value = None

        result = await service.search_history_fallback("user-1", "test")
        assert result["error"] == "no_token"

    async def test_finds_matching_messages(self, service):
        """Should find messages matching query text."""
        token = _make_token()
        service.token_repo.get_by_user_and_provider.return_value = token
        service.token_encryption.get_decrypted_access_token.return_value = "xoxp-test"
        service.participation_repo.get_channel_ids_for_user.return_value = ["C001"]

        with patch("app.services.slack_search.AsyncWebClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.conversations_history.return_value = {
                "messages": [
                    {"text": "Deployment is ready", "user": "U001", "ts": "1700000000.000"},
                    {"text": "unrelated message", "user": "U002", "ts": "1699999000.000"},
                ]
            }
            mock_client.users_info.return_value = {
                "user": {"profile": {"display_name": "Alice"}, "real_name": "Alice"}
            }
            MockClient.return_value = mock_client

            result = await service.search_history_fallback("user-1", "deployment")

        assert len(result["results"]) == 1
        assert "deployment" in result["results"][0]["text_snippet"].lower()
        assert result["scope"] == "fallback"

    async def test_no_matches(self, service):
        """Should return empty results when no matches found."""
        token = _make_token()
        service.token_repo.get_by_user_and_provider.return_value = token
        service.token_encryption.get_decrypted_access_token.return_value = "xoxp-test"
        service.participation_repo.get_channel_ids_for_user.return_value = ["C001"]

        with patch("app.services.slack_search.AsyncWebClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.conversations_history.return_value = {
                "messages": [
                    {"text": "nothing here", "user": "U001", "ts": "1700000000.000"},
                ]
            }
            MockClient.return_value = mock_client

            result = await service.search_history_fallback("user-1", "xyznonexistent")

        assert result["results"] == []


class TestGetSearchContext:
    """Tests for get_search_context()."""

    async def test_returns_joined_data(self, service):
        """Should return channels with summaries joined."""
        ch1 = MagicMock()
        ch1.channel_id = "C001"
        ch1.channel_name = "general"
        ch1.channel_type = "public"
        ch1.member_count = 50
        ch1.participation_rank = 0

        service.participation_repo.get_by_user.return_value = [ch1]

        summary = MagicMock()
        summary.channel_id = "C001"
        summary.summary = "General discussion channel"
        service.summary_repo.get_by_channel_ids.return_value = [summary]

        result = await service.get_search_context("user-1")

        assert len(result) == 1
        assert result[0]["channel_name"] == "general"
        assert result[0]["summary"] == "General discussion channel"

    async def test_empty_when_no_channels(self, service):
        """Should return empty list when user has no channels."""
        service.participation_repo.get_by_user.return_value = []

        result = await service.get_search_context("user-1")
        assert result == []


class TestGetMessages:
    """Tests for get_messages()."""

    async def test_no_token(self, service):
        """Should return error when no token."""
        service.token_repo.get_by_user_and_provider.return_value = None

        result = await service.get_messages("user-1", "C001")
        assert result["error"] == "no_token"

    async def test_returns_formatted_messages(self, service):
        """Should return formatted conversation history."""
        token = _make_token()
        service.token_repo.get_by_user_and_provider.return_value = token
        service.token_encryption.get_decrypted_access_token.return_value = "xoxp-test"

        with patch("app.services.slack_search.AsyncWebClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.conversations_history.return_value = {
                "messages": [
                    {"text": "Hello world", "user": "U001", "ts": "1700000000.000"},
                    {"text": "Hi there", "user": "U002", "ts": "1700001000.000"},
                ]
            }
            mock_client.users_info.return_value = {
                "user": {"profile": {"display_name": "Alice"}, "real_name": "Alice"}
            }
            mock_client.conversations_info.return_value = {
                "channel": {"name": "general", "id": "C001"}
            }
            MockClient.return_value = mock_client

            result = await service.get_messages("user-1", "C001")

        assert result["count"] == 2
        assert result["channel_name"] == "general"
        # Messages are reversed to chronological order (oldest first)
        assert result["messages"][0]["text"] == "Hi there"
        assert result["messages"][1]["text"] == "Hello world"

    async def test_thread_ts_fetches_replies(self, service):
        """Should use conversations.replies when thread_ts is provided."""
        token = _make_token()
        service.token_repo.get_by_user_and_provider.return_value = token
        service.token_encryption.get_decrypted_access_token.return_value = "xoxp-test"

        with patch("app.services.slack_search.AsyncWebClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.conversations_replies.return_value = {
                "messages": [
                    {"text": "Parent", "user": "U001", "ts": "1700000000.000"},
                    {"text": "Reply 1", "user": "U002", "ts": "1700000100.000"},
                ]
            }
            mock_client.users_info.return_value = {
                "user": {"profile": {"display_name": "Alice"}, "real_name": "Alice"}
            }
            mock_client.conversations_info.return_value = {
                "channel": {"name": "general"}
            }
            MockClient.return_value = mock_client

            result = await service.get_messages(
                "user-1", "C001", thread_ts="1700000000.000"
            )

        assert result["count"] == 2
        mock_client.conversations_replies.assert_called_once()

    async def test_include_replies_fetches_nested(self, service):
        """Should fetch thread replies inline when include_replies=True."""
        token = _make_token()
        service.token_repo.get_by_user_and_provider.return_value = token
        service.token_encryption.get_decrypted_access_token.return_value = "xoxp-test"

        with patch("app.services.slack_search.AsyncWebClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.conversations_history.return_value = {
                "messages": [
                    {
                        "text": "Parent msg",
                        "user": "U001",
                        "ts": "1700000000.000",
                        "reply_count": 1,
                    },
                ]
            }
            mock_client.conversations_replies.return_value = {
                "messages": [
                    {"text": "Parent msg", "user": "U001", "ts": "1700000000.000"},
                    {"text": "Reply", "user": "U002", "ts": "1700000100.000"},
                ]
            }
            mock_client.users_info.return_value = {
                "user": {"profile": {"display_name": "Alice"}}
            }
            mock_client.conversations_info.return_value = {
                "channel": {"name": "general"}
            }
            MockClient.return_value = mock_client

            result = await service.get_messages(
                "user-1", "C001", include_replies=True
            )

        # Parent + reply (reply marked as _is_reply)
        assert result["count"] == 2
        mock_client.conversations_replies.assert_called_once()


class TestResolveChannelId:
    """Tests for resolve_channel_id()."""

    async def test_finds_from_participation(self, service):
        """Should find channel from participation data."""
        participation = MagicMock()
        participation.channel_id = "C001"
        service.participation_repo.get_by_channel_name.return_value = participation

        result = await service.resolve_channel_id("user-1", "general")
        assert result == "C001"

    async def test_strips_hash_prefix(self, service):
        """Should strip # prefix from channel name."""
        participation = MagicMock()
        participation.channel_id = "C001"
        service.participation_repo.get_by_channel_name.return_value = participation

        result = await service.resolve_channel_id("user-1", "#general")
        # Should call with stripped name
        service.participation_repo.get_by_channel_name.assert_called_with(
            "user-1", "general"
        )
        assert result == "C001"

    async def test_returns_none_when_not_found(self, service):
        """Should return None when channel not found anywhere."""
        service.participation_repo.get_by_channel_name.return_value = None

        with patch("app.db.repositories.triage.SlackChannelCacheRepository") as MockRepo:
            mock_repo = AsyncMock()
            mock_repo.get_all.return_value = []
            MockRepo.return_value = mock_repo

            result = await service.resolve_channel_id("user-1", "nonexistent")

        assert result is None


class TestListUserChannels:
    """Tests for list_user_channels()."""

    async def test_returns_ranked_channels_with_summaries(self, service):
        """Should return channels ranked by activity with summaries."""
        ch1 = MagicMock()
        ch1.channel_id = "C001"
        ch1.channel_name = "general"
        ch1.channel_type = "public"
        ch1.member_count = 50
        ch1.participation_rank = 0

        service.participation_repo.get_by_user.return_value = [ch1]

        summary = MagicMock()
        summary.channel_id = "C001"
        summary.summary = "General discussion"
        service.summary_repo.get_by_channel_ids.return_value = [summary]

        result = await service.list_user_channels("user-1")

        assert len(result) == 1
        assert result[0]["channel_name"] == "general"
        assert result[0]["summary"] == "General discussion"
        assert result[0]["rank"] == 0

    async def test_empty_when_no_channels(self, service):
        """Should return empty list when user has no channels."""
        service.participation_repo.get_by_user.return_value = []

        result = await service.list_user_channels("user-1")
        assert result == []
