# Phase 6: Slack Integration

## Status: Complete

## Overview

Slack bot integration for Alfred, allowing users to chat via Slack DMs or channel mentions with bi-directional sync between webapp and Slack.

## Implementation Summary

### Database Changes
- [x] Added `slack_user_id` column to users table (migration: `003_add_slack_user_id.py`)
- [x] Updated User model with `slack_user_id` field

### Services Created
- [x] `SlackService` (`app/services/slack.py`)
  - Signature verification for webhook security
  - Send messages to channels/threads
  - Get user info
- [x] `LinkingService` (`app/services/linking.py`)
  - Generate 6-character linking codes
  - Store codes in Redis with 10-minute TTL
  - Validate and consume codes
- [x] `Redis client` (`app/core/redis.py`)
  - Async Redis client singleton

### Repository Updates
- [x] `UserRepository`
  - `get_by_slack_id()` - Find user by Slack ID
  - `link_slack()` - Link Slack account to user
  - `unlink_slack()` - Unlink Slack account
- [x] `SessionRepository`
  - `get_by_slack_thread()` - Find session by Slack thread

### API Endpoints
- [x] `POST /api/slack/events` - Slack Events API webhook
  - Handles `url_verification` challenge
  - Handles `message` and `app_mention` events
  - Event deduplication via Redis (prevents duplicate responses)
  - Background processing for fast response times
- [x] `POST /api/slack/commands` - Slash command handler
  - `/alfred-link` - Generate linking code
- [x] `GET /api/auth/slack-status` - Check linking status
- [x] `POST /api/auth/link-slack` - Link Slack account with code
- [x] `POST /api/auth/unlink-slack` - Unlink Slack account

### Cross-Sync (Bi-directional)
- [x] Slack → Webapp: Messages from Slack create/update sessions visible in webapp
- [x] Webapp → Slack: AI responses posted back to Slack thread
- [x] Webapp → Slack: User messages posted with attribution (`:speech_balloon: user (via webapp):`)

### Frontend
- [x] `SettingsPage` - Settings page with Slack integration section
- [x] `SlackLinkModal` - Modal for entering linking code
- [x] Updated Header with Settings menu item
- [x] Added /settings route

### Tests
- [x] `tests/services/test_slack.py` - SlackService unit tests
- [x] `tests/services/test_linking.py` - LinkingService unit tests
- [x] `tests/api/test_slack.py` - Slack API endpoint tests

## Files Created/Modified

### Created
- `backend/alembic/versions/003_add_slack_user_id.py`
- `backend/app/core/redis.py`
- `backend/app/services/__init__.py`
- `backend/app/services/slack.py`
- `backend/app/services/linking.py`
- `backend/app/api/slack.py`
- `backend/tests/services/__init__.py`
- `backend/tests/services/test_slack.py`
- `backend/tests/services/test_linking.py`
- `backend/tests/api/__init__.py`
- `backend/tests/api/test_slack.py`
- `frontend/src/pages/SettingsPage.tsx`
- `frontend/src/components/settings/SlackLinkModal.tsx`

### Modified
- `backend/app/db/models/user.py` - Added `slack_user_id` field
- `backend/app/db/repositories/user.py` - Added Slack methods
- `backend/app/db/repositories/session.py` - Added `get_by_slack_thread`
- `backend/app/api/__init__.py` - Added Slack router
- `backend/app/api/auth.py` - Added linking endpoints
- `backend/app/api/sessions.py` - Added bi-directional cross-sync
- `backend/app/schemas/auth.py` - Added Slack schemas
- `backend/pyproject.toml` - Added `aiohttp` dependency
- `docker-compose.dev.yml` - Added `uv sync` to startup command
- `frontend/src/App.tsx` - Added Settings route
- `frontend/src/types/index.ts` - Added Slack types
- `frontend/src/components/layout/Header.tsx` - Added Settings menu
- `frontend/src/components/ui/alert-dialog.tsx` - Fixed controlled mode support

## Slack App Configuration

Configure your Slack app with:

1. **Event Subscriptions (Bot Events):**
   - Request URL: `https://<your-domain>/api/slack/events`
   - Subscribe to bot events: `message.channels`, `message.groups`, `message.im`, `app_mention`

2. **Event Subscriptions (User Events - for Focus Mode auto-reply):**
   - Subscribe to events on behalf of users: `message.im`, `message.channels`, `message.groups`
   - This allows Alfred to detect when someone DMs or @mentions a user who is in focus mode

3. **Slash Commands:**
   - Command: `/alfred-link`
   - Request URL: `https://<your-domain>/api/slack/commands`
   - Command: `/alfred-focus`
   - Request URL: `https://<your-domain>/api/slack/commands`

4. **OAuth & Permissions (Bot Token Scopes):**
   - `chat:write`
   - `users:read`
   - `im:history`
   - `channels:history`
   - `app_mentions:read`

5. **OAuth & Permissions (User Token Scopes):**
   - `users.profile:read` - Read user profile
   - `users.profile:write` - Set status during focus mode
   - `im:history` - Receive DM events for focus mode auto-reply
   - `im:read` - View DM info
   - `dnd:write` - Enable/disable Do Not Disturb during focus mode

## Verification Commands

```bash
# Test URL verification
curl -X POST http://localhost:8000/api/slack/events \
  -H "Content-Type: application/json" \
  -d '{"type": "url_verification", "challenge": "test123"}'

# Run tests
docker-compose exec backend pytest tests/services/test_slack.py -v
docker-compose exec backend pytest tests/services/test_linking.py -v
docker-compose exec backend pytest tests/api/test_slack.py -v
```

## Notes

- For local development, use ngrok to expose the webhook endpoint
- Redis is used for:
  - Linking codes with 10-minute TTL
  - Event deduplication with 5-minute TTL (prevents Slack retry duplicates)
- Cross-sync failures are logged but don't fail requests
- Unlinked Slack users receive friendly linking instructions
- Events are processed in background tasks to respond to Slack within 3 seconds
- User messages from webapp appear in Slack with blockquote formatting for clarity

## Diagram

See [slack-flow.md](../diagrams/slack-flow.md) for detailed sequence diagrams.
