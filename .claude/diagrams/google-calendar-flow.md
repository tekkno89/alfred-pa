# Google Calendar Integration Flow

## Google Calendar OAuth Flow

```mermaid
sequenceDiagram
    participant U as User
    participant FE as Frontend
    participant BE as Backend
    participant G as Google
    participant DB as PostgreSQL

    U->>FE: Click "Connect Google Calendar"
    FE->>FE: Show ConnectGoogleCalendarModal<br/>(account label input)
    U->>FE: Enter label (e.g. "personal"), submit
    FE->>BE: GET /api/google-calendar/oauth/url?account_label=personal
    BE->>BE: Validate google_client_id is configured
    BE->>BE: Generate CSRF state token
    BE->>BE: Store state (user_id, account_label)
    BE-->>FE: {url: "https://accounts.google.com/o/oauth2/v2/auth?..."}
    FE->>G: Redirect to Google authorize URL

    U->>G: Select Google account, grant calendar access
    G->>BE: GET /api/google-calendar/oauth/callback?code=...&state=...
    BE->>BE: Validate & consume state token
    BE->>G: POST /token (exchange code for tokens)
    G-->>BE: {access_token, refresh_token, expires_in, scope}
    BE->>G: GET /oauth2/v2/userinfo (fetch email)
    G-->>BE: {email: "user@gmail.com"}
    BE->>BE: Encrypt access_token & refresh_token
    BE->>DB: Upsert UserOAuthToken (provider=google_calendar)
    BE->>FE: Redirect to /settings/integrations?google_calendar_oauth=success
    FE->>U: Show success feedback
```

## Token Refresh

Google OAuth access tokens expire after 1 hour. The `GoogleCalendarService.get_valid_token()` method auto-refreshes using the stored refresh token:

```mermaid
flowchart TD
    A[get_valid_token] --> B{Token exists?}
    B -->|No| C[Return None]
    B -->|Yes| D{Expired?}
    D -->|No| E[Return decrypted token]
    D -->|Yes| F{Has refresh_token?}
    F -->|No| C
    F -->|Yes| G[POST googleapis.com/token<br/>grant_type=refresh_token]
    G --> H{Refresh succeeded?}
    H -->|Yes| I[Store new access_token<br/>Re-use same refresh_token]
    I --> E
    H -->|No| J[Log warning]
    J --> C
```

Note: Google refresh responses do not include a new refresh token, so the original refresh token is re-used on every refresh.

## Disconnect Flow

```mermaid
sequenceDiagram
    participant U as User
    participant FE as Frontend
    participant BE as Backend
    participant G as Google
    participant DB as PostgreSQL

    U->>FE: Click disconnect on a connection
    FE->>BE: DELETE /api/google-calendar/connections/{id}
    BE->>DB: Lookup token, verify ownership
    BE->>BE: Decrypt access_token
    BE->>G: POST /revoke?token=... (best effort)
    BE->>DB: Delete UserOAuthToken
    BE-->>FE: 204 No Content
    FE->>U: Remove connection from list
```

## Multi-Account Support

```mermaid
graph TD
    User[Alfred User] -->|account_label=personal| T1[Google Calendar Token<br/>user@gmail.com<br/>OAuth]
    User -->|account_label=work| T2[Google Calendar Token<br/>user@company.com<br/>OAuth]

    T1 --> DB[(user_oauth_tokens<br/>UNIQUE: user_id + provider + account_label)]
    T2 --> DB
```

Users can connect multiple Google accounts (e.g., personal Gmail + work Workspace) using different account labels. Each connection stores its own encrypted access/refresh tokens.

## Agent Tool: manage_calendar

The `CalendarTool` provides LLM-callable calendar operations. See [tool-system.md](./tool-system.md) for the full tool registry.

| Action | Description |
|--------|-------------|
| `list_events` | Fetch events for a date range (default: today) |
| `create_event` | Create event with title, start/end, attendees, recurrence |
| `update_event` | Modify event (supports `scope`: this/all for recurring) |
| `delete_event` | Remove event |

The tool automatically resolves the user's connected Google account via `account_label` and applies the user's timezone to event times.

## Push Notifications

```mermaid
sequenceDiagram
    participant GC as Google Calendar
    participant BE as Backend
    participant DB as PostgreSQL

    BE->>GC: POST /calendar/v3/calendars/{id}/events/watch
    Note over BE,GC: Subscribe to changes<br/>with webhook URL + channel ID

    GC->>BE: POST /api/google-calendar/push/webhook
    BE->>GC: GET /calendar/v3/events (incremental sync)
    GC-->>BE: Changed events + new syncToken
    BE->>DB: Update cached events
```

Push notification subscriptions auto-renew. Incremental sync uses `syncToken` to fetch only changes since the last sync.

## API Endpoints

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/api/google-calendar/oauth/url?account_label=...` | JWT | Generate Google OAuth authorization URL |
| GET | `/api/google-calendar/oauth/callback?code=...&state=...` | None (state) | Handle OAuth redirect from Google |
| GET | `/api/google-calendar/connections` | JWT | List all connected Google accounts |
| DELETE | `/api/google-calendar/connections/{id}` | JWT | Disconnect a Google account |
| POST | `/api/google-calendar/sync` | JWT | Trigger manual sync |
| POST | `/api/google-calendar/push/subscribe` | JWT | Subscribe to push notifications |
| POST | `/api/google-calendar/push/webhook` | None | Google push notification callback |

## Components

### Backend
- **GoogleCalendarService** (`app/services/google_calendar.py`): OAuth flow, token storage/refresh, Google API calls, connection management
- **Google Calendar API endpoints** (`app/api/google_calendar.py`): REST endpoints for frontend
- **Google Calendar schemas** (`app/schemas/google_calendar.py`): Pydantic request/response models
- **OAuthStateStore** (`app/core/oauth_state.py`): Shared CSRF state management (reused from GitHub)
- **TokenEncryptionService** (`app/services/token_encryption.py`): Envelope encryption for tokens (reused)
- **OAuthTokenRepository** (`app/db/repositories/oauth_token.py`): Token CRUD (reused, provider=google_calendar)

### Frontend
- **CalendarPage** (`pages/CalendarPage.tsx`): Full calendar with month/week/day views, event creation/editing
- **CalendarCard** (`components/dashboard/CalendarCard.tsx`): Dashboard widget showing today's events
- **GoogleCalendarConnectionCard** (`components/settings/GoogleCalendarConnectionCard.tsx`): Connection list with connect/disconnect
- **ConnectGoogleCalendarModal** (`components/settings/ConnectGoogleCalendarModal.tsx`): OAuth connect with account label input
- **useCalendar hook** (`hooks/useCalendar.ts`): React Query hooks for events CRUD, prefetching adjacent ranges
- **useGoogleCalendar hook** (`hooks/useGoogleCalendar.ts`): React Query hooks for connections and OAuth

## OAuth Scopes

The integration requests:
- `openid` — OpenID Connect authentication
- `email` — Access to the user's email (used as the external_account_id)
- `https://www.googleapis.com/auth/calendar` — Full read/write access to Google Calendar (events, calendar list, settings)

## GCP Setup

See the [Google Calendar Integration](#google-calendar-integration) section in README.md for GCP configuration instructions.
