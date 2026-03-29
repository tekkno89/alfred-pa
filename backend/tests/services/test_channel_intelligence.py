"""Tests for ChannelIntelligenceService."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from slack_sdk.errors import SlackApiError

from app.services.channel_intelligence import ChannelIntelligenceService


@pytest.fixture
def mock_db():
    return AsyncMock()


@pytest.fixture
def service(mock_db):
    """Create ChannelIntelligenceService with mocked dependencies."""
    svc = ChannelIntelligenceService(mock_db)
    svc.token_repo = AsyncMock()
    svc.token_encryption = AsyncMock()
    svc.participation_repo = AsyncMock()
    svc.summary_repo = AsyncMock()
    return svc


def _make_token():
    token = MagicMock()
    token.user_id = "user-1"
    token.provider = "slack"
    return token


class TestUpdateParticipation:
    """Tests for update_participation()."""

    async def test_no_token_returns_zero(self, service):
        """Should return 0 when user has no Slack token."""
        service.token_repo.get_by_user_and_provider.return_value = None

        count = await service.update_participation("user-1")
        assert count == 0

    async def test_fetches_and_stores_channels(self, service):
        """Should fetch channels via API and store participation data."""
        token = _make_token()
        service.token_repo.get_by_user_and_provider.return_value = token
        service.token_encryption.get_decrypted_access_token.return_value = "xoxp-test"
        service.participation_repo.upsert_batch.return_value = 2

        mock_response = {
            "channels": [
                {
                    "id": "C001",
                    "name": "general",
                    "is_private": False,
                    "is_mpim": False,
                    "is_member": True,
                    "is_archived": False,
                    "num_members": 50,
                    "updated": 1700000000,
                },
                {
                    "id": "C002",
                    "name": "engineering",
                    "is_private": True,
                    "is_mpim": False,
                    "is_member": True,
                    "is_archived": False,
                    "num_members": 10,
                    "updated": 1699900000,
                },
            ],
            "response_metadata": {"next_cursor": ""},
        }

        with patch(
            "app.services.channel_intelligence.AsyncWebClient"
        ) as MockClient:
            mock_client = AsyncMock()
            mock_client.users_conversations.return_value = mock_response
            MockClient.return_value = mock_client

            count = await service.update_participation("user-1")

        assert count == 2
        service.participation_repo.upsert_batch.assert_called_once()
        # Check the channels passed to upsert_batch
        call_args = service.participation_repo.upsert_batch.call_args
        channels = call_args[0][1]  # positional arg: channels list
        assert len(channels) == 2
        assert channels[0]["channel_id"] == "C001"  # ranked by activity (most recent first)

    async def test_handles_rate_limiting(self, service):
        """Should retry on rate limit errors."""
        token = _make_token()
        service.token_repo.get_by_user_and_provider.return_value = token
        service.token_encryption.get_decrypted_access_token.return_value = "xoxp-test"
        service.participation_repo.upsert_batch.return_value = 1

        mock_error_response = MagicMock()
        mock_error_response.get.return_value = "ratelimited"
        mock_error_response.headers = {"Retry-After": "1"}
        mock_error_response.__getitem__ = lambda self, key: {"error": "ratelimited"}.get(key)

        mock_success_response = {
            "channels": [
                {
                    "id": "C001",
                    "name": "general",
                    "is_private": False,
                    "is_mpim": False,
                    "is_member": True,
                    "is_archived": False,
                    "num_members": 50,
                    "updated": 1700000000,
                },
            ],
            "response_metadata": {"next_cursor": ""},
        }

        with patch(
            "app.services.channel_intelligence.AsyncWebClient"
        ) as MockClient:
            mock_client = AsyncMock()
            # First call: rate limited, second: success
            mock_client.users_conversations.side_effect = [
                SlackApiError(message="ratelimited", response=mock_error_response),
                mock_success_response,
            ]
            MockClient.return_value = mock_client

            with patch("asyncio.sleep", new_callable=AsyncMock):
                count = await service.update_participation("user-1")

        assert count == 1

    async def test_mpim_channel_type(self, service):
        """Should correctly identify mpim channels."""
        token = _make_token()
        service.token_repo.get_by_user_and_provider.return_value = token
        service.token_encryption.get_decrypted_access_token.return_value = "xoxp-test"
        service.participation_repo.upsert_batch.return_value = 1

        mock_response = {
            "channels": [
                {
                    "id": "G001",
                    "name": "mpdm-alice--bob-1",
                    "is_private": True,
                    "is_mpim": True,
                    "is_member": True,
                    "is_archived": False,
                    "num_members": 3,
                    "updated": 1700000000,
                },
            ],
            "response_metadata": {"next_cursor": ""},
        }

        with patch(
            "app.services.channel_intelligence.AsyncWebClient"
        ) as MockClient:
            mock_client = AsyncMock()
            mock_client.users_conversations.return_value = mock_response
            MockClient.return_value = mock_client

            await service.update_participation("user-1")

        call_args = service.participation_repo.upsert_batch.call_args
        channels = call_args[0][1]
        assert channels[0]["channel_type"] == "mpim"


class TestUpdateSummaries:
    """Tests for update_summaries()."""

    async def test_no_tokens_returns_zero(self, service):
        """Should return 0 when no Slack tokens exist."""
        with patch.object(service.db, "execute") as mock_exec:
            mock_result = MagicMock()
            mock_result.scalars.return_value.all.return_value = []
            mock_exec.return_value = mock_result

            count = await service.update_summaries()

        assert count == 0

    async def test_skips_channels_with_few_messages(self, service):
        """Should skip channels with fewer than MIN_SUBSTANTIVE_MESSAGES."""
        token_record = MagicMock()
        token_record.user_id = "user-1"
        token_record.provider = "slack"

        ch1 = MagicMock()
        ch1.channel_id = "C001"
        ch1.channel_name = "quiet-channel"
        ch1.channel_type = "public"
        ch1.member_count = 5
        ch1.is_archived = False

        service.participation_repo.get_by_user.return_value = [ch1]
        service.token_repo.get_by_user_and_provider.return_value = token_record
        service.token_encryption.get_decrypted_access_token.return_value = "xoxp-test"

        with patch.object(service.db, "execute") as mock_exec:
            mock_result = MagicMock()
            mock_result.scalars.return_value.all.return_value = [token_record]
            mock_exec.return_value = mock_result

            with patch(
                "app.services.channel_intelligence.AsyncWebClient"
            ) as MockClient:
                mock_client = AsyncMock()
                # Only 1 substantive message (below threshold of 3)
                mock_client.conversations_history.return_value = {
                    "messages": [
                        {"text": "hello", "ts": "1700000000.000"},
                    ]
                }
                MockClient.return_value = mock_client

                with patch("asyncio.sleep", new_callable=AsyncMock):
                    count = await service.update_summaries()

        assert count == 0
        service.summary_repo.upsert.assert_not_called()

    async def test_generates_summary_with_llm(self, service):
        """Should generate and store an LLM summary for channels with enough messages."""
        token_record = MagicMock()
        token_record.user_id = "user-1"

        ch1 = MagicMock()
        ch1.channel_id = "C001"
        ch1.channel_name = "engineering"
        ch1.channel_type = "public"
        ch1.member_count = 20
        ch1.is_archived = False

        service.participation_repo.get_by_user.return_value = [ch1]
        service.token_repo.get_by_user_and_provider.return_value = token_record
        service.token_encryption.get_decrypted_access_token.return_value = "xoxp-test"

        with patch.object(service.db, "execute") as mock_exec:
            mock_result = MagicMock()
            mock_result.scalars.return_value.all.return_value = [token_record]
            mock_exec.return_value = mock_result

            with patch(
                "app.services.channel_intelligence.AsyncWebClient"
            ) as MockClient:
                mock_client = AsyncMock()
                mock_client.conversations_history.return_value = {
                    "messages": [
                        {"text": "PR review needed", "ts": "1700000000.000"},
                        {"text": "Deploying to staging", "ts": "1699999000.000"},
                        {"text": "CI is green", "ts": "1699998000.000"},
                        {"text": "Bug fix merged", "ts": "1699997000.000"},
                    ]
                }
                MockClient.return_value = mock_client

                with patch(
                    "app.core.llm.get_llm_provider"
                ) as mock_llm:
                    mock_provider = AsyncMock()
                    mock_provider.generate.return_value = (
                        "Engineering discussion about code reviews, deployments, and CI."
                    )
                    mock_llm.return_value = mock_provider

                    with patch("asyncio.sleep", new_callable=AsyncMock):
                        count = await service.update_summaries()

        assert count == 1
        service.summary_repo.upsert.assert_called_once()
        upsert_kwargs = service.summary_repo.upsert.call_args[1]
        assert upsert_kwargs["channel_id"] == "C001"
        assert "Engineering" in upsert_kwargs["summary"]
