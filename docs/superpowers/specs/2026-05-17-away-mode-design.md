# Away Mode Implementation Spec

**Date:** 2026-05-17
**Status:** Approved

## Summary

Implement away mode toggle and configuration for the triage system, allowing users to manually queue messages for catch-up delivery when they return.

## Goals

1. Allow users to toggle away mode on/off via API and UI
2. Configure notify_now behavior during away mode
3. Deliver catch-up digest via Slack DM when toggling off

## Non-Goals

- Automatic away mode based on calendar/status (future enhancement)
- Web app notification for catch-up (Slack DM only)

## API Design

### POST /api/triage/away-mode/toggle

Toggle away mode on/off. When toggled OFF, deliver catch-up digest if items are queued.

**Request:**
```json
{
  "enabled": true
}
```

**Response:**
```json
{
  "enabled": false,
  "queued_count": 5
}
```

**Logic:**
1. Update `away_mode_enabled` in settings
2. If toggling OFF:
   - Query classifications where `user_id=current_user` and `queued_for_digest=True`
   - Group items, send Slack DM catch-up digest
   - Clear `queued_for_digest=False` for delivered items
3. Return current state

### POST /api/triage/away-mode/configure

Configure away mode behavior.

**Request:**
```json
{
  "notify_now_behavior": "push_immediately"
}
```

**Values:** `push_immediately` | `queue_for_catchup`

**Response:** Updated `TriageSettingsResponse`

## Frontend Component

### AwayModeToggle.tsx

- Switch to toggle away mode
- Select dropdown for `notify_now_behavior`
- Status message when enabled
- Queued count display when toggled off

## Data Model

Fields already exist in `TriageUserSettings`:
- `away_mode_enabled: bool` (default: False)
- `away_mode_notify_now_behavior: str` (default: "push_immediately")

Classification tracking:
- `queued_for_digest: bool` on `TriageClassification`

## Implementation Approach

Use direct repository/service calls in endpoints (Approach 1 from brainstorming):
- Toggle endpoint updates settings via `TriageUserSettingsRepository`
- Query queued items via `TriageClassificationRepository`
- Send DM via existing `TriageDeliveryService._send_digest_dm` or Slack service

## Files

**Create:**
- `backend/app/api/triage_away_mode.py`
- `frontend/src/components/triage/AwayModeToggle.tsx`
- `backend/tests/api/test_triage_away_mode.py`

**Modify:**
- `backend/app/main.py` (register router)
- `backend/app/api/__init__.py` (if router aggregation exists)

## Testing

- Unit tests for toggle endpoint (on/off, with/without queued items)
- Unit tests for configure endpoint
- Mock Slack service for catch-up digest testing

## Edge Cases

1. Toggle off with no queued items: Return `queued_count: 0`, no DM sent
2. Multiple toggle requests: Idempotent, just update settings
3. User has no Slack token: Return appropriate error
