"""Tests for GoogleCalendarService."""

import json
from datetime import datetime, timedelta, UTC
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.google_calendar import (
    FULL_SYNC_INTERVAL_SECONDS,
    GoogleCalendarService,
    PROVIDER,
    SyncTokenExpiredError,
    _event_sort_key,
    _normalize_event,
)


@pytest.fixture
def mock_db() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def gcal_service(mock_db) -> GoogleCalendarService:
    """Create a GoogleCalendarService with mocked dependencies."""
    svc = GoogleCalendarService.__new__(GoogleCalendarService)
    svc.db = mock_db
    svc.token_repo = AsyncMock()
    svc.token_encryption = AsyncMock()
    return svc


class TestGetOAuthUrl:
    """Tests for get_oauth_url."""

    @patch("app.services.google_calendar.get_settings")
    def test_generates_url_with_state(self, mock_settings, gcal_service) -> None:
        settings = MagicMock()
        settings.google_client_id = "test-client-id"
        settings.google_calendar_oauth_redirect_uri = (
            "http://localhost:8000/api/google-calendar/oauth/callback"
        )
        mock_settings.return_value = settings

        url = gcal_service.get_oauth_url("user-1", "personal")

        assert "client_id=test-client-id" in url
        assert "accounts.google.com" in url
        assert "state=" in url
        assert "access_type=offline" in url
        assert "prompt=consent" in url
        assert "auth%2Fcalendar" in url

    @patch("app.services.google_calendar.get_settings")
    def test_raises_if_not_configured(self, mock_settings, gcal_service) -> None:
        settings = MagicMock()
        settings.google_client_id = ""
        mock_settings.return_value = settings

        with pytest.raises(ValueError, match="Google OAuth is not configured"):
            gcal_service.get_oauth_url("user-1")


class TestExchangeCode:
    """Tests for exchange_code."""

    @pytest.mark.asyncio
    @patch("app.services.google_calendar.get_settings")
    async def test_exchanges_code_successfully(
        self, mock_settings, gcal_service
    ) -> None:
        settings = MagicMock()
        settings.google_client_id = "client-id"
        settings.google_client_secret = "client-secret"
        settings.google_calendar_oauth_redirect_uri = "http://localhost/callback"
        mock_settings.return_value = settings

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "access_token": "ya29.test",
            "refresh_token": "1//test-refresh",
            "expires_in": 3600,
            "scope": "openid email https://www.googleapis.com/auth/calendar.readonly",
            "token_type": "Bearer",
        }

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post.return_value = mock_response
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            result = await gcal_service.exchange_code("test-code")

        assert result["access_token"] == "ya29.test"
        assert result["refresh_token"] == "1//test-refresh"

    @pytest.mark.asyncio
    @patch("app.services.google_calendar.get_settings")
    async def test_raises_on_error(self, mock_settings, gcal_service) -> None:
        settings = MagicMock()
        settings.google_client_id = "client-id"
        settings.google_client_secret = "client-secret"
        settings.google_calendar_oauth_redirect_uri = "http://localhost/callback"
        mock_settings.return_value = settings

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "error": "invalid_grant",
            "error_description": "The code has already been redeemed.",
        }

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post.return_value = mock_response
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            with pytest.raises(ValueError, match="already been redeemed"):
                await gcal_service.exchange_code("bad-code")


class TestGetUserEmail:
    """Tests for get_user_email."""

    @pytest.mark.asyncio
    async def test_returns_email(self, gcal_service) -> None:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"email": "user@example.com"}

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get.return_value = mock_response
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            result = await gcal_service.get_user_email("ya29.test")

        assert result == "user@example.com"

    @pytest.mark.asyncio
    async def test_raises_on_api_error(self, gcal_service) -> None:
        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_response.text = "Unauthorized"

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get.return_value = mock_response
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            with pytest.raises(ValueError, match="401"):
                await gcal_service.get_user_email("invalid-token")


class TestStoreOAuthToken:
    """Tests for store_oauth_token."""

    @pytest.mark.asyncio
    async def test_stores_token_with_email(self, gcal_service) -> None:
        mock_token = MagicMock()
        mock_token.id = "token-id"
        mock_token.provider = PROVIDER
        mock_token.account_label = "personal"
        mock_token.external_account_id = "user@example.com"

        gcal_service.token_encryption.store_encrypted_token.return_value = mock_token

        # Mock get_user_email
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"email": "user@example.com"}

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get.return_value = mock_response
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            result = await gcal_service.store_oauth_token(
                user_id="user-1",
                token_data={
                    "access_token": "ya29.test",
                    "refresh_token": "1//refresh",
                    "expires_in": 3600,
                    "scope": "openid email calendar.readonly",
                },
                account_label="personal",
            )

        assert result.external_account_id == "user@example.com"
        store_call = gcal_service.token_encryption.store_encrypted_token.call_args
        assert store_call[1]["provider"] == PROVIDER
        assert store_call[1]["account_label"] == "personal"
        assert store_call[1]["external_account_id"] == "user@example.com"
        assert store_call[1]["refresh_token"] == "1//refresh"


class TestRefreshAccessToken:
    """Tests for refresh_access_token."""

    @pytest.mark.asyncio
    @patch("app.services.google_calendar.get_settings")
    async def test_refreshes_successfully(self, mock_settings, gcal_service) -> None:
        settings = MagicMock()
        settings.google_client_id = "client-id"
        settings.google_client_secret = "client-secret"
        mock_settings.return_value = settings

        mock_token = MagicMock()
        mock_token.user_id = "user-1"
        mock_token.account_label = "personal"
        mock_token.external_account_id = "user@example.com"

        gcal_service.token_encryption.get_decrypted_refresh_token.return_value = (
            "1//refresh"
        )

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "access_token": "ya29.new-token",
            "expires_in": 3600,
            "scope": "openid email calendar.readonly",
        }

        mock_stored = MagicMock()
        gcal_service.token_encryption.store_encrypted_token.return_value = mock_stored

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post.return_value = mock_response
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            result = await gcal_service.refresh_access_token(mock_token)

        assert result == mock_stored
        store_call = gcal_service.token_encryption.store_encrypted_token.call_args
        assert store_call[1]["access_token"] == "ya29.new-token"
        # Refresh token should be re-used from original
        assert store_call[1]["refresh_token"] == "1//refresh"

    @pytest.mark.asyncio
    async def test_raises_without_refresh_token(self, gcal_service) -> None:
        mock_token = MagicMock()
        gcal_service.token_encryption.get_decrypted_refresh_token.return_value = None

        with pytest.raises(ValueError, match="No refresh token available"):
            await gcal_service.refresh_access_token(mock_token)


class TestGetValidToken:
    """Tests for get_valid_token."""

    @pytest.mark.asyncio
    async def test_returns_token_when_not_expired(self, gcal_service) -> None:
        mock_token = MagicMock()
        mock_token.expires_at = None

        gcal_service.token_repo.get_by_user_provider_and_label.return_value = (
            mock_token
        )
        gcal_service.token_encryption.get_decrypted_access_token.return_value = (
            "ya29.valid"
        )

        result = await gcal_service.get_valid_token("user-1", "default")
        assert result == "ya29.valid"

    @pytest.mark.asyncio
    async def test_returns_none_when_no_token(self, gcal_service) -> None:
        gcal_service.token_repo.get_by_user_provider_and_label.return_value = None
        result = await gcal_service.get_valid_token("user-1")
        assert result is None


class TestDeleteConnection:
    """Tests for delete_connection."""

    @pytest.mark.asyncio
    async def test_deletes_with_revoke(self, gcal_service) -> None:
        mock_token = MagicMock()
        mock_token.user_id = "user-1"
        gcal_service.token_repo.get.return_value = mock_token
        gcal_service.token_encryption.get_decrypted_access_token.return_value = (
            "ya29.test"
        )
        gcal_service.token_repo.delete_by_id.return_value = True

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            result = await gcal_service.delete_connection("token-1", "user-1")

        assert result is True

    @pytest.mark.asyncio
    async def test_returns_false_when_not_found(self, gcal_service) -> None:
        gcal_service.token_repo.get.return_value = None
        result = await gcal_service.delete_connection("nonexistent", "user-1")
        assert result is False

    @pytest.mark.asyncio
    async def test_returns_false_when_wrong_user(self, gcal_service) -> None:
        mock_token = MagicMock()
        mock_token.user_id = "other-user"
        gcal_service.token_repo.get.return_value = mock_token

        result = await gcal_service.delete_connection("token-1", "user-1")
        assert result is False

    @pytest.mark.asyncio
    async def test_cleans_up_sync_stores(self, gcal_service) -> None:
        mock_token = MagicMock()
        mock_token.user_id = "user-1"
        mock_token.account_label = "personal"
        gcal_service.token_repo.get.return_value = mock_token
        gcal_service.token_encryption.get_decrypted_access_token.return_value = (
            "ya29.test"
        )
        gcal_service.token_repo.delete_by_id.return_value = True

        mock_redis = AsyncMock()
        mock_redis.scan_iter = MagicMock(return_value=AsyncIterMock([]))

        with (
            patch("httpx.AsyncClient") as mock_client_cls,
            patch.object(gcal_service, "_get_redis", return_value=mock_redis),
        ):
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            await gcal_service.delete_connection("token-1", "user-1")

        # _cleanup_account_stores was called (scan_iter was invoked for 4 prefixes)
        assert mock_redis.scan_iter.call_count == 4


class AsyncIterMock:
    """Async iterator mock for redis.scan_iter."""

    def __init__(self, items):
        self.items = list(items)

    def __aiter__(self):
        return self

    async def __anext__(self):
        if not self.items:
            raise StopAsyncIteration
        return self.items.pop(0)


def _make_raw_event(event_id: str, summary: str, start: str, end: str, calendar_id: str = "cal-1") -> dict:
    """Create a raw Google Calendar API event."""
    return {
        "id": event_id,
        "summary": summary,
        "start": {"dateTime": start},
        "end": {"dateTime": end},
        "status": "confirmed",
    }


def _make_normalized_event(event_id: str, summary: str, start: str, end: str, calendar_id: str = "cal-1") -> dict:
    """Create a normalized event dict."""
    return _normalize_event(
        _make_raw_event(event_id, summary, start, end, calendar_id),
        calendar_id,
    )


@pytest.fixture
def mock_redis():
    """Create a mock Redis client with hash operations."""
    redis = AsyncMock()
    redis.hgetall = AsyncMock(return_value={})
    redis.hset = AsyncMock()
    redis.hdel = AsyncMock()
    redis.delete = AsyncMock()
    redis.get = AsyncMock(return_value=None)
    redis.set = AsyncMock()
    redis.scan_iter = MagicMock(return_value=AsyncIterMock([]))
    return redis


class TestSyncTokenExpiredError:
    """Tests for HTTP 410 → SyncTokenExpiredError."""

    @pytest.mark.asyncio
    async def test_api_request_raises_on_410(self, gcal_service) -> None:
        mock_response = MagicMock()
        mock_response.status_code = 410
        mock_response.json.return_value = {"error": {"message": "Gone"}}

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.request.return_value = mock_response
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            with pytest.raises(SyncTokenExpiredError):
                await gcal_service._api_request(
                    "GET", "https://example.com", "token"
                )


class TestPaginatedEventsList:
    """Tests for _paginated_events_list."""

    @pytest.mark.asyncio
    async def test_single_page(self, gcal_service) -> None:
        items = [_make_raw_event("e1", "Event 1", "2026-03-07T10:00:00Z", "2026-03-07T11:00:00Z")]
        gcal_service._api_request = AsyncMock(return_value={
            "items": items,
            "nextSyncToken": "sync-token-1",
        })

        result_items, sync_token = await gcal_service._paginated_events_list(
            "token", "cal-1", {"timeMin": "2026-03-01"}
        )

        assert len(result_items) == 1
        assert sync_token == "sync-token-1"
        gcal_service._api_request.assert_called_once()

    @pytest.mark.asyncio
    async def test_multiple_pages(self, gcal_service) -> None:
        page1 = {
            "items": [_make_raw_event("e1", "Event 1", "2026-03-07T10:00:00Z", "2026-03-07T11:00:00Z")],
            "nextPageToken": "page-2",
        }
        page2 = {
            "items": [_make_raw_event("e2", "Event 2", "2026-03-08T10:00:00Z", "2026-03-08T11:00:00Z")],
            "nextSyncToken": "sync-token-final",
        }
        gcal_service._api_request = AsyncMock(side_effect=[page1, page2])

        result_items, sync_token = await gcal_service._paginated_events_list(
            "token", "cal-1", {"timeMin": "2026-03-01"}
        )

        assert len(result_items) == 2
        assert result_items[0]["id"] == "e1"
        assert result_items[1]["id"] == "e2"
        assert sync_token == "sync-token-final"
        assert gcal_service._api_request.call_count == 2


class TestFullSync:
    """Tests for _full_sync."""

    @pytest.mark.asyncio
    async def test_full_sync_stores_events_and_token(self, gcal_service, mock_redis) -> None:
        gcal_service.get_valid_token = AsyncMock(return_value="ya29.test")
        gcal_service._get_redis = AsyncMock(return_value=mock_redis)

        raw_events = [
            _make_raw_event("e1", "Meeting", "2026-03-07T10:00:00Z", "2026-03-07T11:00:00Z"),
            _make_raw_event("e2", "Lunch", "2026-03-07T12:00:00Z", "2026-03-07T13:00:00Z"),
        ]

        gcal_service._api_request = AsyncMock(return_value={
            "items": raw_events,
            "nextSyncToken": "sync-abc",
        })

        await gcal_service._full_sync("user-1", "default", "cal-1")

        # Verify events stored
        mock_redis.hset.assert_called_once()
        stored_mapping = mock_redis.hset.call_args[1]["mapping"]
        assert "e1" in stored_mapping
        assert "e2" in stored_mapping

        # Verify sync token and start marker stored
        set_calls = [c for c in mock_redis.set.call_args_list]
        keys_set = [c[0][0] for c in set_calls]
        assert "gcal:sync:user-1:default:cal-1" in keys_set
        assert "gcal:sync:start:user-1:default:cal-1" in keys_set

    @pytest.mark.asyncio
    async def test_full_sync_clears_existing_store_first(self, gcal_service, mock_redis) -> None:
        gcal_service.get_valid_token = AsyncMock(return_value="ya29.test")
        gcal_service._get_redis = AsyncMock(return_value=mock_redis)
        gcal_service._api_request = AsyncMock(return_value={
            "items": [],
            "nextSyncToken": "sync-abc",
        })

        await gcal_service._full_sync("user-1", "default", "cal-1")

        # Should have called delete to clear existing store
        mock_redis.delete.assert_called()

    @pytest.mark.asyncio
    async def test_full_sync_skips_cancelled_events(self, gcal_service, mock_redis) -> None:
        gcal_service.get_valid_token = AsyncMock(return_value="ya29.test")
        gcal_service._get_redis = AsyncMock(return_value=mock_redis)

        raw_events = [
            _make_raw_event("e1", "Active", "2026-03-07T10:00:00Z", "2026-03-07T11:00:00Z"),
            {**_make_raw_event("e2", "Cancelled", "2026-03-07T12:00:00Z", "2026-03-07T13:00:00Z"), "status": "cancelled"},
        ]

        gcal_service._api_request = AsyncMock(return_value={
            "items": raw_events,
            "nextSyncToken": "sync-abc",
        })

        await gcal_service._full_sync("user-1", "default", "cal-1")

        stored_mapping = mock_redis.hset.call_args[1]["mapping"]
        assert "e1" in stored_mapping
        assert "e2" not in stored_mapping


class TestIncrementalSync:
    """Tests for _incremental_sync."""

    @pytest.mark.asyncio
    async def test_upserts_modified_events(self, gcal_service, mock_redis) -> None:
        gcal_service.get_valid_token = AsyncMock(return_value="ya29.test")
        gcal_service._get_redis = AsyncMock(return_value=mock_redis)

        raw_events = [
            _make_raw_event("e1", "Updated Meeting", "2026-03-07T10:00:00Z", "2026-03-07T11:00:00Z"),
        ]

        gcal_service._api_request = AsyncMock(return_value={
            "items": raw_events,
            "nextSyncToken": "sync-new",
        })

        await gcal_service._incremental_sync("user-1", "default", "cal-1", "sync-old")

        # Event upserted
        mock_redis.hset.assert_called_once()
        stored_mapping = mock_redis.hset.call_args[1]["mapping"]
        assert "e1" in stored_mapping
        evt = json.loads(stored_mapping["e1"])
        assert evt["title"] == "Updated Meeting"

        # New sync token saved
        mock_redis.set.assert_called_once_with(
            "gcal:sync:user-1:default:cal-1", "sync-new"
        )

    @pytest.mark.asyncio
    async def test_removes_cancelled_events(self, gcal_service, mock_redis) -> None:
        gcal_service.get_valid_token = AsyncMock(return_value="ya29.test")
        gcal_service._get_redis = AsyncMock(return_value=mock_redis)

        raw_events = [
            {**_make_raw_event("e-del", "Deleted", "2026-03-07T10:00:00Z", "2026-03-07T11:00:00Z"), "status": "cancelled"},
        ]

        gcal_service._api_request = AsyncMock(return_value={
            "items": raw_events,
            "nextSyncToken": "sync-new",
        })

        await gcal_service._incremental_sync("user-1", "default", "cal-1", "sync-old")

        # Cancelled event removed
        mock_redis.hdel.assert_called_once()
        assert "e-del" in mock_redis.hdel.call_args[0]

        # No upsert for cancelled events
        mock_redis.hset.assert_not_called()

    @pytest.mark.asyncio
    async def test_410_triggers_full_sync(self, gcal_service, mock_redis) -> None:
        gcal_service.get_valid_token = AsyncMock(return_value="ya29.test")
        gcal_service._get_redis = AsyncMock(return_value=mock_redis)

        gcal_service._api_request = AsyncMock(
            side_effect=SyncTokenExpiredError("410")
        )
        gcal_service._full_sync = AsyncMock()

        await gcal_service._incremental_sync("user-1", "default", "cal-1", "expired-token")

        gcal_service._full_sync.assert_called_once_with("user-1", "default", "cal-1")

    @pytest.mark.asyncio
    async def test_mixed_upsert_and_delete(self, gcal_service, mock_redis) -> None:
        gcal_service.get_valid_token = AsyncMock(return_value="ya29.test")
        gcal_service._get_redis = AsyncMock(return_value=mock_redis)

        raw_events = [
            _make_raw_event("e1", "New Event", "2026-03-07T10:00:00Z", "2026-03-07T11:00:00Z"),
            {**_make_raw_event("e2", "Deleted", "2026-03-07T12:00:00Z", "2026-03-07T13:00:00Z"), "status": "cancelled"},
        ]

        gcal_service._api_request = AsyncMock(return_value={
            "items": raw_events,
            "nextSyncToken": "sync-new",
        })

        await gcal_service._incremental_sync("user-1", "default", "cal-1", "sync-old")

        # Upserted
        mock_redis.hset.assert_called_once()
        assert "e1" in mock_redis.hset.call_args[1]["mapping"]

        # Deleted
        mock_redis.hdel.assert_called_once()
        assert "e2" in mock_redis.hdel.call_args[0]


class TestEnsureSynced:
    """Tests for _ensure_synced."""

    @pytest.mark.asyncio
    async def test_calls_incremental_when_sync_token_exists(self, gcal_service, mock_redis) -> None:
        fresh_time = (datetime.now(UTC) - timedelta(seconds=60)).isoformat()

        async def mock_get(key):
            if "gcal:sync:last_full:" in key:
                return fresh_time
            if "gcal:sync:" in key:
                return "existing-sync-token"
            return None

        mock_redis.get = AsyncMock(side_effect=mock_get)
        gcal_service._get_redis = AsyncMock(return_value=mock_redis)
        gcal_service._incremental_sync = AsyncMock()
        gcal_service._full_sync = AsyncMock()

        await gcal_service._ensure_synced("user-1", "default", "cal-1")

        gcal_service._incremental_sync.assert_called_once_with(
            "user-1", "default", "cal-1", "existing-sync-token"
        )
        gcal_service._full_sync.assert_not_called()

    @pytest.mark.asyncio
    async def test_calls_full_sync_when_no_token(self, gcal_service, mock_redis) -> None:
        mock_redis.get.return_value = None
        gcal_service._get_redis = AsyncMock(return_value=mock_redis)
        gcal_service._incremental_sync = AsyncMock()
        gcal_service._full_sync = AsyncMock()

        await gcal_service._ensure_synced("user-1", "default", "cal-1")

        gcal_service._full_sync.assert_called_once_with("user-1", "default", "cal-1")
        gcal_service._incremental_sync.assert_not_called()


class TestListEventsSync:
    """Tests for the new sync-based list_events."""

    @pytest.mark.asyncio
    async def test_uses_sync_store(self, gcal_service, mock_redis) -> None:
        mock_redis.get.return_value = None  # No sync start boundary
        gcal_service._get_redis = AsyncMock(return_value=mock_redis)
        gcal_service._ensure_synced = AsyncMock()
        gcal_service._event_store_get_range = AsyncMock(return_value=[
            _make_normalized_event("e1", "Event 1", "2026-03-07T10:00:00Z", "2026-03-07T11:00:00Z"),
            _make_normalized_event("e2", "Event 2", "2026-03-07T09:00:00Z", "2026-03-07T10:00:00Z"),
        ])

        events = await gcal_service.list_events(
            "user-1", "default", "cal-1",
            "2026-03-07T00:00:00Z", "2026-03-08T00:00:00Z",
        )

        gcal_service._ensure_synced.assert_called_once()
        # Events sorted by start
        assert events[0]["start"] == "2026-03-07T09:00:00Z"
        assert events[1]["start"] == "2026-03-07T10:00:00Z"

    @pytest.mark.asyncio
    async def test_falls_back_to_direct_for_old_queries(self, gcal_service, mock_redis) -> None:
        # sync_start is 90 days ago, but query is older
        mock_redis.get.return_value = "2025-12-01T00:00:00"
        gcal_service._get_redis = AsyncMock(return_value=mock_redis)
        gcal_service._fetch_events_direct = AsyncMock(return_value=[])
        gcal_service._ensure_synced = AsyncMock()

        events = await gcal_service.list_events(
            "user-1", "default", "cal-1",
            "2025-01-01T00:00:00Z", "2025-02-01T00:00:00Z",
        )

        gcal_service._fetch_events_direct.assert_called_once()
        gcal_service._ensure_synced.assert_not_called()


class TestEventStoreRangeFilter:
    """Tests for _event_store_get_range."""

    @pytest.mark.asyncio
    async def test_filters_events_by_range(self, gcal_service, mock_redis) -> None:
        e_in_range = _make_normalized_event("e1", "In Range", "2026-03-07T10:00:00Z", "2026-03-07T11:00:00Z")
        e_out_range = _make_normalized_event("e2", "Out of Range", "2026-03-08T10:00:00Z", "2026-03-08T11:00:00Z")

        mock_redis.hgetall.return_value = {
            "e1": json.dumps(e_in_range),
            "e2": json.dumps(e_out_range),
        }
        gcal_service._get_redis = AsyncMock(return_value=mock_redis)

        events = await gcal_service._event_store_get_range(
            "user-1", "default", "cal-1",
            "2026-03-07T00:00:00Z", "2026-03-08T00:00:00Z",
        )

        assert len(events) == 1
        assert events[0]["id"] == "e1"

    @pytest.mark.asyncio
    async def test_includes_multi_day_events_overlapping_range(self, gcal_service, mock_redis) -> None:
        # Multi-day all-day event: Mar 2-9, query is Mar 5-6
        e_multi = _normalize_event(
            {"id": "e-multi", "summary": "On-call", "start": {"date": "2026-03-02"}, "end": {"date": "2026-03-09"}, "status": "confirmed"},
            "cal-1",
        )
        e_outside = _normalize_event(
            {"id": "e-outside", "summary": "Old", "start": {"date": "2026-02-01"}, "end": {"date": "2026-02-02"}, "status": "confirmed"},
            "cal-1",
        )

        mock_redis.hgetall.return_value = {
            "e-multi": json.dumps(e_multi),
            "e-outside": json.dumps(e_outside),
        }
        gcal_service._get_redis = AsyncMock(return_value=mock_redis)

        events = await gcal_service._event_store_get_range(
            "user-1", "default", "cal-1",
            "2026-03-05T00:00:00Z", "2026-03-06T00:00:00Z",
        )

        assert len(events) == 1
        assert events[0]["id"] == "e-multi"


class TestWriteOpsUpdateStore:
    """Tests that create/update/delete update the event store."""

    @pytest.mark.asyncio
    async def test_create_event_upserts_to_store(self, gcal_service, mock_redis) -> None:
        gcal_service.get_valid_token = AsyncMock(return_value="ya29.test")
        gcal_service._get_redis = AsyncMock(return_value=mock_redis)

        created = _make_raw_event("new-1", "New Event", "2026-03-07T10:00:00Z", "2026-03-07T11:00:00Z")
        gcal_service._api_request = AsyncMock(return_value=created)

        result = await gcal_service.create_event(
            "user-1", "default", "cal-1", {"summary": "New Event"}
        )

        assert result["id"] == "new-1"
        mock_redis.hset.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_event_upserts_to_store(self, gcal_service, mock_redis) -> None:
        gcal_service.get_valid_token = AsyncMock(return_value="ya29.test")
        gcal_service._get_redis = AsyncMock(return_value=mock_redis)

        updated = _make_raw_event("e1", "Updated", "2026-03-07T10:00:00Z", "2026-03-07T11:00:00Z")
        gcal_service._api_request = AsyncMock(return_value=updated)

        result = await gcal_service.update_event(
            "user-1", "default", "cal-1", "e1", {"summary": "Updated"}
        )

        assert result["title"] == "Updated"
        mock_redis.hset.assert_called_once()

    @pytest.mark.asyncio
    async def test_delete_event_removes_from_store(self, gcal_service, mock_redis) -> None:
        gcal_service.get_valid_token = AsyncMock(return_value="ya29.test")
        gcal_service._get_redis = AsyncMock(return_value=mock_redis)
        gcal_service._api_request = AsyncMock(return_value={})

        await gcal_service.delete_event("user-1", "default", "cal-1", "e1")

        mock_redis.hdel.assert_called_once()
        assert "e1" in mock_redis.hdel.call_args[0]


class TestHandlePushNotification:
    """Tests for push notification with incremental sync."""

    @pytest.mark.asyncio
    async def test_incremental_sync_on_push(self, gcal_service, mock_redis) -> None:
        watch_info = json.dumps({
            "user_id": "user-1",
            "account_label": "default",
            "calendar_id": "cal-1",
            "resource_id": "res-1",
        })

        call_count = 0
        async def mock_get(key):
            nonlocal call_count
            call_count += 1
            if "gcal:watch:" in key:
                return watch_info
            if "gcal:sync:" in key:
                return "sync-token-abc"
            return None

        mock_redis.get = AsyncMock(side_effect=mock_get)
        gcal_service._get_redis = AsyncMock(return_value=mock_redis)
        gcal_service._incremental_sync = AsyncMock()

        await gcal_service.handle_push_notification("channel-1", "res-1")

        gcal_service._incremental_sync.assert_called_once_with(
            "user-1", "default", "cal-1", "sync-token-abc"
        )

    @pytest.mark.asyncio
    async def test_no_sync_token_skips_sync(self, gcal_service, mock_redis) -> None:
        watch_info = json.dumps({
            "user_id": "user-1",
            "account_label": "default",
            "calendar_id": "cal-1",
            "resource_id": "res-1",
        })

        async def mock_get(key):
            if "gcal:watch:" in key:
                return watch_info
            return None

        mock_redis.get = AsyncMock(side_effect=mock_get)
        gcal_service._get_redis = AsyncMock(return_value=mock_redis)
        gcal_service._incremental_sync = AsyncMock()

        await gcal_service.handle_push_notification("channel-1", "res-1")

        gcal_service._incremental_sync.assert_not_called()

    @pytest.mark.asyncio
    async def test_sync_failure_clears_store(self, gcal_service, mock_redis) -> None:
        watch_info = json.dumps({
            "user_id": "user-1",
            "account_label": "default",
            "calendar_id": "cal-1",
            "resource_id": "res-1",
        })

        async def mock_get(key):
            if "gcal:watch:" in key:
                return watch_info
            if "gcal:sync:" in key:
                return "sync-token-abc"
            return None

        mock_redis.get = AsyncMock(side_effect=mock_get)
        gcal_service._get_redis = AsyncMock(return_value=mock_redis)
        gcal_service._incremental_sync = AsyncMock(side_effect=Exception("API error"))

        await gcal_service.handle_push_notification("channel-1", "res-1")

        # Store should be cleared so next read triggers full sync
        mock_redis.delete.assert_called_once()


class TestRedisKeyBuilders:
    """Tests for static key builder methods."""

    def test_store_key(self) -> None:
        assert GoogleCalendarService._store_key("u1", "default", "cal-1") == "gcal:store:u1:default:cal-1"

    def test_sync_token_key(self) -> None:
        assert GoogleCalendarService._sync_token_key("u1", "work", "cal-2") == "gcal:sync:u1:work:cal-2"

    def test_sync_start_key(self) -> None:
        assert GoogleCalendarService._sync_start_key("u1", "default", "cal-1") == "gcal:sync:start:u1:default:cal-1"

    def test_last_full_sync_key(self) -> None:
        assert GoogleCalendarService._last_full_sync_key("u1", "default", "cal-1") == "gcal:sync:last_full:u1:default:cal-1"


class TestStalenessFullResync:
    """Tests for periodic full re-sync staleness mechanism."""

    @pytest.mark.asyncio
    async def test_full_sync_stores_last_full_timestamp(self, gcal_service, mock_redis) -> None:
        gcal_service.get_valid_token = AsyncMock(return_value="ya29.test")
        gcal_service._get_redis = AsyncMock(return_value=mock_redis)
        gcal_service._api_request = AsyncMock(return_value={
            "items": [],
            "nextSyncToken": "sync-abc",
        })

        await gcal_service._full_sync("user-1", "default", "cal-1")

        set_calls = [c for c in mock_redis.set.call_args_list]
        keys_set = [c[0][0] for c in set_calls]
        assert "gcal:sync:last_full:user-1:default:cal-1" in keys_set

    @pytest.mark.asyncio
    async def test_ensure_synced_forces_full_when_last_full_missing(self, gcal_service, mock_redis) -> None:
        """When sync token exists but last_full marker is missing, force full sync."""
        call_count = 0
        async def mock_get(key):
            nonlocal call_count
            call_count += 1
            if "gcal:sync:last_full:" in key:
                return None
            if "gcal:sync:" in key:
                return "existing-sync-token"
            return None

        mock_redis.get = AsyncMock(side_effect=mock_get)
        gcal_service._get_redis = AsyncMock(return_value=mock_redis)
        gcal_service._incremental_sync = AsyncMock()
        gcal_service._full_sync = AsyncMock()

        await gcal_service._ensure_synced("user-1", "default", "cal-1")

        gcal_service._full_sync.assert_called_once_with("user-1", "default", "cal-1")
        gcal_service._incremental_sync.assert_not_called()

    @pytest.mark.asyncio
    async def test_ensure_synced_forces_full_when_stale(self, gcal_service, mock_redis) -> None:
        """When last full sync is older than FULL_SYNC_INTERVAL_SECONDS, force full sync."""
        stale_time = (datetime.now(UTC) - timedelta(seconds=FULL_SYNC_INTERVAL_SECONDS + 60)).isoformat()

        async def mock_get(key):
            if "gcal:sync:last_full:" in key:
                return stale_time
            if "gcal:sync:" in key:
                return "existing-sync-token"
            return None

        mock_redis.get = AsyncMock(side_effect=mock_get)
        gcal_service._get_redis = AsyncMock(return_value=mock_redis)
        gcal_service._incremental_sync = AsyncMock()
        gcal_service._full_sync = AsyncMock()

        await gcal_service._ensure_synced("user-1", "default", "cal-1")

        gcal_service._full_sync.assert_called_once_with("user-1", "default", "cal-1")
        gcal_service._incremental_sync.assert_not_called()

    @pytest.mark.asyncio
    async def test_ensure_synced_incremental_when_fresh(self, gcal_service, mock_redis) -> None:
        """When last full sync is recent, use incremental sync."""
        fresh_time = (datetime.now(UTC) - timedelta(seconds=60)).isoformat()

        async def mock_get(key):
            if "gcal:sync:last_full:" in key:
                return fresh_time
            if "gcal:sync:" in key:
                return "existing-sync-token"
            return None

        mock_redis.get = AsyncMock(side_effect=mock_get)
        gcal_service._get_redis = AsyncMock(return_value=mock_redis)
        gcal_service._incremental_sync = AsyncMock()
        gcal_service._full_sync = AsyncMock()

        await gcal_service._ensure_synced("user-1", "default", "cal-1")

        gcal_service._incremental_sync.assert_called_once_with(
            "user-1", "default", "cal-1", "existing-sync-token"
        )
        gcal_service._full_sync.assert_not_called()

    @pytest.mark.asyncio
    async def test_event_store_clear_deletes_last_full_key(self, gcal_service, mock_redis) -> None:
        gcal_service._get_redis = AsyncMock(return_value=mock_redis)

        await gcal_service._event_store_clear("user-1", "default", "cal-1")

        delete_args = mock_redis.delete.call_args[0]
        assert "gcal:sync:last_full:user-1:default:cal-1" in delete_args


class TestDeduplication:
    """Tests for event deduplication across calendars."""

    @pytest.mark.asyncio
    async def test_deduplicates_by_event_id(self, gcal_service) -> None:
        """Same event in two calendars should appear only once."""
        e1 = _make_normalized_event("shared-event", "Eng Leads", "2026-03-17T10:00:00Z", "2026-03-17T11:00:00Z", "cal-1")
        e2 = _make_normalized_event("shared-event", "Eng Leads", "2026-03-17T10:00:00Z", "2026-03-17T11:00:00Z", "cal-2")
        e3 = _make_normalized_event("unique-event", "Standup", "2026-03-17T09:00:00Z", "2026-03-17T09:30:00Z", "cal-1")

        gcal_service.list_events = AsyncMock(side_effect=[[e1, e3], [e2]])

        configs = [
            {"calendar_id": "cal-1", "account_label": "default", "color": "#4285f4"},
            {"calendar_id": "cal-2", "account_label": "default", "color": "#0b8043"},
        ]

        events = await gcal_service.list_events_for_user(
            "user-1", configs,
            "2026-03-17T00:00:00Z", "2026-03-18T00:00:00Z",
        )

        ids = [e["id"] for e in events]
        assert ids.count("shared-event") == 1
        assert len(events) == 2

    @pytest.mark.asyncio
    async def test_first_calendar_color_wins(self, gcal_service) -> None:
        """The first calendar in config order determines the event's color."""
        e1 = _make_normalized_event("shared", "Meeting", "2026-03-17T10:00:00Z", "2026-03-17T11:00:00Z", "cal-1")
        e2 = _make_normalized_event("shared", "Meeting", "2026-03-17T10:00:00Z", "2026-03-17T11:00:00Z", "cal-2")

        gcal_service.list_events = AsyncMock(side_effect=[[e1], [e2]])

        configs = [
            {"calendar_id": "cal-1", "account_label": "default", "color": "#ff0000"},
            {"calendar_id": "cal-2", "account_label": "default", "color": "#00ff00"},
        ]

        events = await gcal_service.list_events_for_user(
            "user-1", configs,
            "2026-03-17T00:00:00Z", "2026-03-18T00:00:00Z",
        )

        assert len(events) == 1
        assert events[0]["color"] == "#ff0000"


class TestEventSortKey:
    """Tests for the _event_sort_key helper."""

    def test_all_day_before_timed(self) -> None:
        all_day = {"start": "2026-03-17", "all_day": True}
        timed = {"start": "2026-03-17T08:00:00Z", "all_day": False}
        assert _event_sort_key(all_day) < _event_sort_key(timed)

    def test_timed_events_sorted_by_timestamp(self) -> None:
        early = {"start": "2026-03-17T08:00:00-07:00", "all_day": False}
        late = {"start": "2026-03-17T18:00:00+00:00", "all_day": False}
        assert _event_sort_key(early) < _event_sort_key(late)

    def test_cross_timezone_ordering(self) -> None:
        """Event at 8am Pacific (15:00 UTC) should sort after 10am UTC."""
        utc_morning = {"start": "2026-03-17T10:00:00+00:00", "all_day": False}
        pacific_morning = {"start": "2026-03-17T08:00:00-07:00", "all_day": False}
        assert _event_sort_key(utc_morning) < _event_sort_key(pacific_morning)

    def test_different_days(self) -> None:
        day1 = {"start": "2026-03-16T23:00:00Z", "all_day": False}
        day2 = {"start": "2026-03-17T01:00:00Z", "all_day": False}
        assert _event_sort_key(day1) < _event_sort_key(day2)
