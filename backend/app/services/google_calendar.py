"""Google Calendar service for OAuth and API operations."""

import hashlib
import hmac
import json
import logging
import secrets
import uuid
from datetime import datetime, UTC, timedelta
from typing import Any
from urllib.parse import urlencode

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.oauth_state import consume_oauth_state, store_oauth_state
from app.db.models import UserOAuthToken
from app.db.repositories import OAuthTokenRepository
from app.services.token_encryption import TokenEncryptionService

logger = logging.getLogger(__name__)

GOOGLE_AUTHORIZE_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v2/userinfo"
GOOGLE_REVOKE_URL = "https://oauth2.googleapis.com/revoke"
GOOGLE_CALENDAR_API = "https://www.googleapis.com/calendar/v3"

GOOGLE_CALENDAR_SCOPES = "openid email https://www.googleapis.com/auth/calendar"

PROVIDER = "google_calendar"

CALENDAR_COLOR_PALETTE = [
    "#4285f4", "#0b8043", "#8e24aa", "#d50000", "#f4511e",
    "#f6bf26", "#039be5", "#616161", "#33b679", "#e67c73",
]

# Redis cache TTLs
CACHE_TTL_CALENDARS = 300  # 5 minutes
CACHE_TTL_EVENTS = 300  # 5 minutes (invalidated on write and by push notifications)


def _normalize_event(event: dict, calendar_id: str, color: str = "#4285f4") -> dict:
    """Normalize a Google Calendar event into a consistent format."""
    start = event.get("start", {})
    end = event.get("end", {})
    all_day = "date" in start

    return {
        "id": event["id"],
        "calendar_id": calendar_id,
        "title": event.get("summary", "(No title)"),
        "description": event.get("description"),
        "location": event.get("location"),
        "start": start.get("date") if all_day else start.get("dateTime"),
        "end": end.get("date") if all_day else end.get("dateTime"),
        "all_day": all_day,
        "color": color,
        "status": event.get("status", "confirmed"),
        "html_link": event.get("htmlLink"),
        "attendees": [
            {"email": a["email"], "response_status": a.get("responseStatus", "needsAction")}
            for a in event.get("attendees", [])
        ],
        "recurring_event_id": event.get("recurringEventId"),
        "recurrence": event.get("recurrence"),
        "creator": event.get("creator", {}).get("email"),
        "organizer": event.get("organizer", {}).get("email"),
    }


class GoogleCalendarService:
    """Service for Google Calendar OAuth operations."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.token_repo = OAuthTokenRepository(db)
        self.token_encryption = TokenEncryptionService(db)

    def get_oauth_url(self, user_id: str, account_label: str = "default") -> str:
        """Generate Google OAuth authorization URL."""
        settings = get_settings()

        if not settings.google_client_id:
            raise ValueError("Google OAuth is not configured")

        state = secrets.token_urlsafe(32)
        store_oauth_state(state, user_id, account_label)

        params = {
            "client_id": settings.google_client_id,
            "redirect_uri": settings.google_calendar_oauth_redirect_uri,
            "response_type": "code",
            "scope": GOOGLE_CALENDAR_SCOPES,
            "access_type": "offline",
            "prompt": "consent",
            "state": state,
        }

        return f"{GOOGLE_AUTHORIZE_URL}?{urlencode(params)}"

    async def exchange_code(self, code: str) -> dict:
        """Exchange OAuth authorization code for access/refresh tokens."""
        settings = get_settings()

        async with httpx.AsyncClient() as client:
            response = await client.post(
                GOOGLE_TOKEN_URL,
                data={
                    "client_id": settings.google_client_id,
                    "client_secret": settings.google_client_secret,
                    "code": code,
                    "grant_type": "authorization_code",
                    "redirect_uri": settings.google_calendar_oauth_redirect_uri,
                },
            )

        data = response.json()
        if "error" in data:
            raise ValueError(
                f"Google OAuth error: {data.get('error_description', data['error'])}"
            )

        return data

    async def get_user_email(self, access_token: str) -> str:
        """Get the authenticated user's email address."""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                GOOGLE_USERINFO_URL,
                headers={"Authorization": f"Bearer {access_token}"},
            )

        if response.status_code != 200:
            raise ValueError(
                f"Google API error: {response.status_code} {response.text}"
            )

        return response.json().get("email", "")

    async def store_oauth_token(
        self,
        user_id: str,
        token_data: dict,
        account_label: str = "default",
    ) -> UserOAuthToken:
        """Store Google Calendar OAuth token after code exchange."""
        access_token = token_data["access_token"]
        refresh_token = token_data.get("refresh_token")
        scope = token_data.get("scope")

        expires_at = None
        if "expires_in" in token_data:
            expires_at = datetime.now(UTC).replace(tzinfo=None) + timedelta(
                seconds=token_data["expires_in"]
            )

        email = await self.get_user_email(access_token)

        return await self.token_encryption.store_encrypted_token(
            user_id=user_id,
            provider=PROVIDER,
            access_token=access_token,
            refresh_token=refresh_token,
            scope=scope,
            expires_at=expires_at,
            account_label=account_label,
            external_account_id=email,
        )

    async def refresh_access_token(self, token: UserOAuthToken) -> UserOAuthToken:
        """Refresh an expired access token using the stored refresh token."""
        settings = get_settings()

        refresh_token = await self.token_encryption.get_decrypted_refresh_token(token)
        if not refresh_token:
            raise ValueError("No refresh token available")

        async with httpx.AsyncClient() as client:
            response = await client.post(
                GOOGLE_TOKEN_URL,
                data={
                    "client_id": settings.google_client_id,
                    "client_secret": settings.google_client_secret,
                    "grant_type": "refresh_token",
                    "refresh_token": refresh_token,
                },
            )

        data = response.json()
        if "error" in data:
            raise ValueError(
                f"Token refresh failed: {data.get('error_description', data['error'])}"
            )

        expires_at = None
        if "expires_in" in data:
            expires_at = datetime.now(UTC).replace(tzinfo=None) + timedelta(
                seconds=data["expires_in"]
            )

        # Google refresh responses don't include a new refresh_token,
        # so re-use the existing one
        return await self.token_encryption.store_encrypted_token(
            user_id=token.user_id,
            provider=PROVIDER,
            access_token=data["access_token"],
            refresh_token=refresh_token,
            scope=data.get("scope"),
            expires_at=expires_at,
            account_label=token.account_label,
            external_account_id=token.external_account_id,
        )

    async def get_valid_token(
        self, user_id: str, account_label: str = "default"
    ) -> str | None:
        """Get a valid access token, auto-refreshing if expired."""
        token = await self.token_repo.get_by_user_provider_and_label(
            user_id, PROVIDER, account_label
        )
        if not token:
            return None

        if token.expires_at and token.expires_at < datetime.now(UTC).replace(
            tzinfo=None
        ):
            try:
                token = await self.refresh_access_token(token)
            except ValueError:
                logger.warning(
                    f"Failed to refresh Google Calendar token for user {user_id}"
                )
                return None

        return await self.token_encryption.get_decrypted_access_token(token)

    async def delete_connection(self, connection_id: str, user_id: str) -> bool:
        """Delete a Google Calendar connection by ID with ownership check.

        Best-effort revoke the token with Google before deleting.
        """
        token = await self.token_repo.get(connection_id)
        if not token or token.user_id != user_id:
            return False

        # Best-effort revoke
        try:
            access_token = await self.token_encryption.get_decrypted_access_token(
                token
            )
            async with httpx.AsyncClient() as client:
                await client.post(
                    GOOGLE_REVOKE_URL,
                    params={"token": access_token},
                )
        except Exception:
            logger.warning("Failed to revoke Google token (best effort)")

        return await self.token_repo.delete_by_id(connection_id, user_id)

    # ------------------------------------------------------------------
    # Calendar API helpers
    # ------------------------------------------------------------------

    async def _api_request(
        self,
        method: str,
        url: str,
        access_token: str,
        **kwargs: Any,
    ) -> dict | list:
        """Make an authenticated Google Calendar API request."""
        headers = {"Authorization": f"Bearer {access_token}"}
        async with httpx.AsyncClient() as client:
            response = await client.request(method, url, headers=headers, **kwargs)

        if response.status_code == 204:
            return {}

        data = response.json()
        if response.status_code >= 400:
            error_msg = data.get("error", {}).get("message", response.text)
            raise ValueError(f"Google Calendar API error ({response.status_code}): {error_msg}")

        return data

    async def _get_redis(self):
        """Get Redis client, returning None if unavailable."""
        try:
            from app.core.redis import get_redis
            return await get_redis()
        except Exception:
            return None

    async def _cache_get(self, key: str) -> Any | None:
        """Read from Redis cache."""
        redis_client = await self._get_redis()
        if not redis_client:
            return None
        try:
            data = await redis_client.get(key)
            return json.loads(data) if data else None
        except Exception:
            return None

    async def _cache_set(self, key: str, value: Any, ttl: int) -> None:
        """Write to Redis cache."""
        redis_client = await self._get_redis()
        if not redis_client:
            return
        try:
            await redis_client.set(key, json.dumps(value), ex=ttl)
        except Exception:
            pass

    async def _cache_invalidate_events(self, user_id: str) -> None:
        """Invalidate all cached events for a user."""
        redis_client = await self._get_redis()
        if not redis_client:
            return
        try:
            pattern = f"gcal:events:{user_id}:*"
            keys = []
            async for key in redis_client.scan_iter(match=pattern, count=100):
                keys.append(key)
            if keys:
                await redis_client.delete(*keys)
        except Exception:
            pass

    async def list_calendars(
        self, user_id: str, account_label: str = "default"
    ) -> list[dict]:
        """List all calendars for a connected account."""
        cache_key = f"gcal:calendars:{user_id}:{account_label}"
        cached = await self._cache_get(cache_key)
        if cached is not None:
            return cached

        access_token = await self.get_valid_token(user_id, account_label)
        if not access_token:
            return []

        url = f"{GOOGLE_CALENDAR_API}/users/me/calendarList"
        data = await self._api_request("GET", url, access_token)

        calendars = []
        for item in data.get("items", []):
            calendars.append({
                "id": item["id"],
                "name": item.get("summary", item["id"]),
                "description": item.get("description"),
                "primary": item.get("primary", False),
                "background_color": item.get("backgroundColor"),
                "foreground_color": item.get("foregroundColor"),
                "access_role": item.get("accessRole", "reader"),
            })

        await self._cache_set(cache_key, calendars, CACHE_TTL_CALENDARS)
        return calendars

    def _get_months_for_range(self, time_min: str, time_max: str) -> list[tuple[int, int]]:
        """Return list of (year, month) tuples covering the requested range."""
        from datetime import datetime as dt

        try:
            start = dt.fromisoformat(time_min.replace("Z", "+00:00"))
            end = dt.fromisoformat(time_max.replace("Z", "+00:00"))
        except ValueError:
            # Fallback: parse just the date portion
            start = dt.fromisoformat(time_min[:10])
            end = dt.fromisoformat(time_max[:10])

        months = []
        current = start.replace(day=1)
        while current <= end:
            months.append((current.year, current.month))
            if current.month == 12:
                current = current.replace(year=current.year + 1, month=1)
            else:
                current = current.replace(month=current.month + 1)
        return months

    async def _fetch_month_events(
        self,
        user_id: str,
        account_label: str,
        calendar_id: str,
        year: int,
        month: int,
    ) -> list[dict]:
        """Fetch and cache a full calendar month of events."""
        cache_key = f"gcal:events:{user_id}:{account_label}:{calendar_id}:{year}-{month:02d}"
        cached = await self._cache_get(cache_key)
        if cached is not None:
            return cached

        access_token = await self.get_valid_token(user_id, account_label)
        if not access_token:
            return []

        # Full month boundaries in UTC
        from calendar import monthrange
        _, last_day = monthrange(year, month)
        month_start = f"{year}-{month:02d}-01T00:00:00Z"
        if month == 12:
            month_end = f"{year + 1}-01-01T00:00:00Z"
        else:
            month_end = f"{year}-{month + 1:02d}-01T00:00:00Z"

        url = f"{GOOGLE_CALENDAR_API}/calendars/{calendar_id}/events"
        params = {
            "timeMin": month_start,
            "timeMax": month_end,
            "singleEvents": "true",
            "orderBy": "startTime",
            "maxResults": "2500",
        }
        data = await self._api_request("GET", url, access_token, params=params)

        events = [
            _normalize_event(e, calendar_id)
            for e in data.get("items", [])
            if e.get("status") != "cancelled"
        ]

        await self._cache_set(cache_key, events, CACHE_TTL_EVENTS)
        return events

    async def list_events(
        self,
        user_id: str,
        account_label: str,
        calendar_id: str,
        time_min: str,
        time_max: str,
    ) -> list[dict]:
        """List events from a specific calendar within a time range.

        Fetches full calendar months and caches by month boundary so that
        different views (week, month) within the same month share cache.
        """
        months = self._get_months_for_range(time_min, time_max)
        all_events = []

        for year, month in months:
            events = await self._fetch_month_events(
                user_id, account_label, calendar_id, year, month
            )
            all_events.extend(events)

        # Filter to the exact requested range
        filtered = [
            e for e in all_events
            if e.get("start", "") >= time_min[:19] and e.get("start", "") < time_max[:19]
        ]
        return filtered

    async def create_event(
        self,
        user_id: str,
        account_label: str,
        calendar_id: str,
        event_data: dict,
    ) -> dict:
        """Create a new calendar event."""
        access_token = await self.get_valid_token(user_id, account_label)
        if not access_token:
            raise ValueError("No valid Google Calendar token available")

        url = f"{GOOGLE_CALENDAR_API}/calendars/{calendar_id}/events"
        data = await self._api_request("POST", url, access_token, json=event_data)

        await self._cache_invalidate_events(user_id)
        return _normalize_event(data, calendar_id)

    async def update_event(
        self,
        user_id: str,
        account_label: str,
        calendar_id: str,
        event_id: str,
        event_data: dict,
    ) -> dict:
        """Update an existing calendar event (partial update)."""
        access_token = await self.get_valid_token(user_id, account_label)
        if not access_token:
            raise ValueError("No valid Google Calendar token available")

        url = f"{GOOGLE_CALENDAR_API}/calendars/{calendar_id}/events/{event_id}"
        data = await self._api_request("PATCH", url, access_token, json=event_data)

        await self._cache_invalidate_events(user_id)
        return _normalize_event(data, calendar_id)

    async def delete_event(
        self,
        user_id: str,
        account_label: str,
        calendar_id: str,
        event_id: str,
    ) -> None:
        """Delete a calendar event."""
        access_token = await self.get_valid_token(user_id, account_label)
        if not access_token:
            raise ValueError("No valid Google Calendar token available")

        url = f"{GOOGLE_CALENDAR_API}/calendars/{calendar_id}/events/{event_id}"
        await self._api_request("DELETE", url, access_token)

        await self._cache_invalidate_events(user_id)

    async def list_all_calendars_for_user(self, user_id: str) -> list[dict]:
        """List all calendars across all connected Google Calendar accounts."""
        tokens = await self.token_repo.get_all_by_user_and_provider(user_id, PROVIDER)
        all_calendars = []

        for token in tokens:
            try:
                calendars = await self.list_calendars(user_id, token.account_label)
                for cal in calendars:
                    cal["account_label"] = token.account_label
                    cal["account_email"] = token.external_account_id
                all_calendars.extend(calendars)
            except Exception:
                logger.warning(
                    f"Failed to list calendars for account {token.account_label}"
                )

        return all_calendars

    async def list_events_for_user(
        self,
        user_id: str,
        calendar_configs: list[dict],
        time_min: str,
        time_max: str,
    ) -> list[dict]:
        """Fetch events from all visible calendars, annotated with color, sorted by start."""
        all_events = []

        for config in calendar_configs:
            account_label = config.get("account_label", "default")
            calendar_id = config["calendar_id"]
            color = config.get("color", "#4285f4")

            try:
                events = await self.list_events(
                    user_id, account_label, calendar_id, time_min, time_max
                )
                for event in events:
                    event["color"] = color
                    event["account_label"] = account_label
                all_events.extend(events)
            except Exception:
                logger.warning(
                    f"Failed to fetch events from {calendar_id} ({account_label})"
                )

        # Sort by start time
        all_events.sort(key=lambda e: e.get("start", ""))
        return all_events

    # ------------------------------------------------------------------
    # Push notification (watch) management
    # ------------------------------------------------------------------

    # Redis keys for watch channels:
    #   gcal:watch:{channel_id} → JSON{user_id, account_label, calendar_id, resource_id, expiration}
    #   gcal:watches:{user_id}  → set of channel_ids

    WATCH_TTL = 7 * 24 * 3600  # Google max is 7 days; we renew before expiry

    @staticmethod
    def _generate_channel_token(channel_id: str) -> str:
        """Generate an HMAC token for a watch channel.

        Uses JWT_SECRET as the signing key so only this server can produce
        valid tokens. Google echoes this back in X-Goog-Channel-Token on
        every notification so we can verify the request is legitimate.
        """
        settings = get_settings()
        return hmac.new(
            settings.jwt_secret.encode(),
            channel_id.encode(),
            hashlib.sha256,
        ).hexdigest()

    @staticmethod
    def verify_channel_token(channel_id: str, token: str) -> bool:
        """Verify that a channel token is valid."""
        expected = GoogleCalendarService._generate_channel_token(channel_id)
        return hmac.compare_digest(expected, token)

    async def watch_calendar(
        self,
        user_id: str,
        account_label: str,
        calendar_id: str,
    ) -> dict | None:
        """Register a push notification watch for a calendar.

        Returns the watch info dict or None if webhook URL is not configured.
        """
        settings = get_settings()
        webhook_url = settings.google_calendar_webhook_url
        if not webhook_url:
            return None

        access_token = await self.get_valid_token(user_id, account_label)
        if not access_token:
            return None

        channel_id = str(uuid.uuid4())
        channel_token = self._generate_channel_token(channel_id)

        # Google requires an absolute HTTPS URL
        url = f"{GOOGLE_CALENDAR_API}/calendars/{calendar_id}/events/watch"
        body = {
            "id": channel_id,
            "type": "web_hook",
            "address": webhook_url,
            "token": channel_token,
        }

        try:
            data = await self._api_request("POST", url, access_token, json=body)
        except ValueError as e:
            logger.warning(f"Failed to register calendar watch: {e}")
            return None

        resource_id = data.get("resourceId", "")
        expiration = int(data.get("expiration", 0))

        # Store mapping in Redis
        watch_info = {
            "user_id": user_id,
            "account_label": account_label,
            "calendar_id": calendar_id,
            "resource_id": resource_id,
            "channel_id": channel_id,
            "expiration": expiration,
        }

        redis_client = await self._get_redis()
        if redis_client:
            try:
                await redis_client.set(
                    f"gcal:watch:{channel_id}",
                    json.dumps(watch_info),
                    ex=self.WATCH_TTL,
                )
                await redis_client.sadd(f"gcal:watches:{user_id}", channel_id)
            except Exception:
                logger.warning("Failed to store watch info in Redis")

        logger.info(
            f"Registered calendar watch: user={user_id} cal={calendar_id} channel={channel_id}"
        )
        return watch_info

    async def unwatch_calendar(self, channel_id: str, resource_id: str) -> None:
        """Stop a push notification watch."""
        # We need a valid token — look up the watch info first
        redis_client = await self._get_redis()
        if not redis_client:
            return

        try:
            data = await redis_client.get(f"gcal:watch:{channel_id}")
            if not data:
                return
            watch_info = json.loads(data)
        except Exception:
            return

        user_id = watch_info["user_id"]
        account_label = watch_info["account_label"]
        access_token = await self.get_valid_token(user_id, account_label)
        if not access_token:
            return

        try:
            url = f"{GOOGLE_CALENDAR_API}/channels/stop"
            await self._api_request(
                "POST", url, access_token,
                json={"id": channel_id, "resourceId": resource_id},
            )
        except ValueError:
            logger.warning(f"Failed to stop watch channel {channel_id} (best effort)")

        # Clean up Redis
        try:
            await redis_client.delete(f"gcal:watch:{channel_id}")
            await redis_client.srem(f"gcal:watches:{user_id}", channel_id)
        except Exception:
            pass

    async def handle_push_notification(self, channel_id: str, resource_id: str) -> None:
        """Handle an incoming push notification from Google Calendar.

        Invalidates the cached events for the relevant user/calendar.
        """
        redis_client = await self._get_redis()
        if not redis_client:
            return

        try:
            data = await redis_client.get(f"gcal:watch:{channel_id}")
            if not data:
                logger.debug(f"Unknown watch channel: {channel_id}")
                return
            watch_info = json.loads(data)
        except Exception:
            return

        user_id = watch_info["user_id"]
        logger.info(f"Calendar push notification: user={user_id} channel={channel_id}")
        await self._cache_invalidate_events(user_id)

    async def ensure_watches_for_user(self, user_id: str) -> None:
        """Ensure all visible calendars have active watches. Idempotent."""
        settings = get_settings()
        if not settings.google_calendar_webhook_url:
            return

        redis_client = await self._get_redis()
        if not redis_client:
            return

        # Get existing watches
        try:
            existing_channels = await redis_client.smembers(f"gcal:watches:{user_id}")
        except Exception:
            existing_channels = set()

        # Build set of calendars already watched
        watched_cals: set[str] = set()
        for ch_id in existing_channels:
            try:
                data = await redis_client.get(f"gcal:watch:{ch_id}")
                if data:
                    info = json.loads(data)
                    watched_cals.add(f"{info['account_label']}:{info['calendar_id']}")
            except Exception:
                pass

        # Get all calendars for this user
        all_calendars = await self.list_all_calendars_for_user(user_id)

        for cal in all_calendars:
            cal_key = f"{cal.get('account_label', 'default')}:{cal['id']}"
            if cal_key not in watched_cals:
                await self.watch_calendar(
                    user_id,
                    cal.get("account_label", "default"),
                    cal["id"],
                )
