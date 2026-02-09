# Phase 7: Focus Mode Feature

## Status: Complete

## Overview
Implemented a Focus Mode feature that integrates with Slack to help users minimize distractions.

## Features Implemented

### Focus Mode Core
- [x] Toggle focus mode on/off
- [x] Optional duration with auto-disable
- [x] Pomodoro mode with work/break cycles
- [x] Customizable auto-reply messages
- [x] VIP whitelist for bypass

### Slack Integration
- [x] `/alfred-focus` slash command
- [x] Auto-reply to DMs when user is in focus mode (via user event subscriptions)
- [x] Auto-reply to @mentions in channels when user is in focus mode
- [x] Personalized auto-reply message showing who is unavailable
- [x] Bypass button for urgent messages
- [x] Slack OAuth for status control (set status to "Focus Mode")
- [x] Slack DND (Do Not Disturb) - automatically enabled/disabled with focus mode
- [x] DND prevents dock bounce and notifications during focus mode

### Notifications
- [x] SSE endpoint for real-time webapp notifications
- [x] Webhook subscriptions for external services
- [x] Browser notifications for bypass alerts

### Background Jobs (ARQ)
- [x] Scheduled phase transitions for pomodoro timer
- [x] Proper job cancellation when stopping/skipping
- [x] Frontend polling fallback (SSE doesn't work across containers)

### Frontend
- [x] Focus page with toggle and quick actions
- [x] Pomodoro timer component
- [x] Focus settings page
- [x] VIP list management
- [x] Webhook management page
- [x] Notification banner for bypass alerts
- [x] Focus mode indicator in header

## Files Created

### Backend
- `alembic/versions/004_add_focus_mode_tables.py` - Database migration
- `app/db/models/focus.py` - FocusModeState, FocusSettings, FocusVIPList models
- `app/db/models/webhook.py` - WebhookSubscription model
- `app/db/models/oauth_token.py` - UserOAuthToken model
- `app/db/repositories/focus.py` - Focus repositories
- `app/db/repositories/webhook.py` - Webhook repository
- `app/db/repositories/oauth_token.py` - OAuth token repository
- `app/services/focus.py` - FocusModeService
- `app/services/notifications.py` - NotificationService
- `app/services/slack_user.py` - SlackUserService
- `app/api/focus.py` - Focus mode endpoints
- `app/api/webhooks.py` - Webhook endpoints
- `app/api/notifications.py` - SSE notifications endpoint
- `app/schemas/focus.py` - Focus mode schemas (with UTC datetime serialization)
- `app/schemas/webhook.py` - Webhook schemas
- `app/worker/scheduler.py` - ARQ job scheduling with proper cancellation
- `app/worker/tasks.py` - Pomodoro transition task
- `app/worker/main.py` - Worker configuration

### Frontend
- `src/pages/FocusPage.tsx` - Main focus mode page
- `src/pages/FocusSettingsPage.tsx` - Focus settings page
- `src/pages/WebhooksPage.tsx` - Webhook management page
- `src/components/focus/FocusToggle.tsx` - Focus toggle button
- `src/components/focus/PomodoroTimer.tsx` - Pomodoro timer
- `src/components/focus/VipList.tsx` - VIP list management
- `src/components/settings/WebhookForm.tsx` - Webhook creation form
- `src/components/notifications/NotificationProvider.tsx` - Notification context
- `src/components/notifications/NotificationBanner.tsx` - Bypass alert banner
- `src/hooks/useFocusMode.ts` - Focus mode React Query hooks
- `src/hooks/useNotifications.ts` - SSE notification hook

### Modified Files
- `app/db/models/user.py` - Added focus/webhook relationships
- `app/db/models/__init__.py` - Export new models
- `app/db/repositories/__init__.py` - Export new repositories
- `app/services/__init__.py` - Export new services
- `app/schemas/__init__.py` - Export new schemas
- `app/api/__init__.py` - Register new routers
- `app/api/slack.py` - Focus mode check, /alfred-focus command, interactive handler
- `app/api/auth.py` - Slack OAuth endpoints
- `app/core/config.py` - Slack OAuth settings
- `frontend/src/App.tsx` - New routes, notification provider
- `frontend/src/pages/SettingsPage.tsx` - Focus mode section
- `frontend/src/components/layout/Header.tsx` - Focus mode indicator
- `frontend/src/types/index.ts` - New type definitions

## API Endpoints

### Focus Mode
- `POST /api/focus/enable` - Enable focus mode
- `POST /api/focus/disable` - Disable focus mode
- `GET /api/focus/status` - Get current status
- `POST /api/focus/pomodoro/start` - Start pomodoro
- `POST /api/focus/pomodoro/skip` - Skip pomodoro phase
- `GET /api/focus/settings` - Get settings
- `PUT /api/focus/settings` - Update settings
- `GET /api/focus/vip` - List VIP users
- `POST /api/focus/vip` - Add VIP user
- `DELETE /api/focus/vip/{id}` - Remove VIP user

### Webhooks
- `GET /api/webhooks` - List webhooks
- `POST /api/webhooks` - Create webhook
- `GET /api/webhooks/{id}` - Get webhook
- `PUT /api/webhooks/{id}` - Update webhook
- `DELETE /api/webhooks/{id}` - Delete webhook
- `POST /api/webhooks/{id}/test` - Test webhook

### Notifications
- `GET /api/notifications/subscribe` - SSE stream

### Slack OAuth
- `GET /api/auth/slack/oauth/authorize` - Start OAuth flow
- `GET /api/auth/slack/oauth/callback` - OAuth callback
- `GET /api/auth/slack/oauth/status` - Check OAuth status
- `DELETE /api/auth/slack/oauth` - Revoke OAuth

## Slack Commands
- `/alfred-focus` - Toggle focus mode
- `/alfred-focus on [duration]` - Enable with duration
- `/alfred-focus off` - Disable
- `/alfred-focus status` - Show status
- `/alfred-focus pomodoro` - Start pomodoro

## Database Tables
- `focus_mode_state` - Current focus state per user
- `focus_settings` - Focus mode settings per user
- `focus_vip_list` - VIP whitelist per user
- `webhook_subscriptions` - Webhook subscriptions per user
- `user_oauth_tokens` - OAuth tokens per user

## Slack App Requirements

For full focus mode functionality, the Slack app needs:

### User Token Scopes
- `users.profile:read` - Read user profile
- `users.profile:write` - Set focus mode status
- `im:history` - Receive DM events for auto-reply
- `im:read` - View DM info
- `dnd:write` - Enable/disable Do Not Disturb

### User Event Subscriptions
- `message.im` - Subscribe to events on behalf of users to detect incoming DMs

Users must complete the Slack OAuth flow (Settings → Connect Slack) to grant these permissions.

## Known Limitations

### SSE Cross-Container Issue
SSE notifications from the ARQ worker to the frontend don't work because the worker and backend run in separate containers with separate memory spaces. The `NotificationService._sse_clients` dict is in-memory and not shared.

**Current workaround**: Frontend polls every second when the pomodoro timer reaches 0:00, until the phase changes.

**Future fix**: Implement Redis pub/sub - worker publishes to Redis, backend subscribes and pushes to SSE clients.

## Verification Steps

### Run migration
```bash
docker-compose exec backend alembic upgrade head
```

### Test focus mode
1. Enable focus mode from webapp
2. Send DM to Slack → verify auto-reply
3. Click bypass button → verify notification in webapp
4. Add VIP user → verify they bypass focus mode
5. Start pomodoro → verify timer works
6. Register webhook → verify events received
7. Test `/alfred-focus` slash command
