# Phase 15: Triage Enhancement - Read Detection & Conversation Grouping

## Goal

Enable Alfred to act as a true personal assistant for focus by:
1. Not notifying users of messages they've already read or responded to
2. Intelligently grouping messages into conversations for cleaner digest summaries

## Architecture

```
Digest time:
  → Get all classified messages for timeframe
  → Group by channel/thread/DM
  → LLM determines which messages are related (conversations)
  → Check if user responded to each conversation (reaction or message after)
  → Create summary for unresponded conversations
  → Send digest
```

## Phase 1: Reaction Tracking ✅ COMPLETE

- [x] Subscribe to `reaction_added` Slack events
- [x] Cache user reactions in Redis: `triage:reactions:{user_id}:{channel_id}` → SET of message_ts
- [x] Add `user_reacted_at` field to `TriageClassification` model
- [x] Update reaction handling to mark classification as reacted
- [x] Add database migration
- [x] Add `reactions:read` to required Slack scopes
- [x] Add repository methods `mark_user_reacted` and `mark_user_responded`

## Phase 2: Conversation Grouping ✅ COMPLETE

- [x] Create `DigestGrouper` service (`backend/app/services/digest_grouper.py`)
- [x] Implement thread grouping (deterministic - same `thread_ts`)
- [x] Implement channel grouping (LLM identifies conversation boundaries)
- [x] Create `ConversationGroup` data structure
- [x] Add `group_channel_messages_with_llm()` for semantic grouping

## Phase 3: Response Detection at Digest Time ✅ COMPLETE

- [x] Create `DigestResponseChecker` service (`backend/app/services/digest_response_checker.py`)
- [x] Check user reactions against conversations
- [x] Check user messages after conversation (fetch history from Slack)
- [x] Filter out responded conversations before summarization
- [x] Integrate with `send_digest` task via `use_conversation_grouping` flag

## Phase 4: Intelligent Summaries & Frontend ✅ COMPLETE

- [x] Add `prepare_conversation_digest()` method to TriageDeliveryService
- [x] Add `create_conversation_summary()` for per-conversation summaries
- [x] Add `send_conversation_digest_dm()` for conversation-grouped digest
- [x] Add `user_reacted_at` and `user_responded_at` to backend schema
- [x] Update frontend `TriageClassification` type
- [x] Update `SummaryCard` to show response status (reacted/responded)

## Testing ✅ COMPLETE

- [x] Write unit tests for `DigestGrouper` (37 tests passing)
- [x] Write unit tests for `DigestResponseChecker`
- [x] Write integration tests for digest flow (10 tests passing)
- [x] Test conversation grouping logic
- [x] Test LLM-based grouping
- [x] Test response filtering

## Key Files Created/Modified

| File | Purpose |
|------|---------|
| `backend/app/services/digest_grouper.py` | **NEW** - Conversation grouping logic |
| `backend/app/services/digest_response_checker.py` | **NEW** - Response detection |
| `backend/app/api/slack.py` | Added `handle_reaction_added_event()` |
| `backend/app/api/auth.py` | Added `reactions:read` to required scopes |
| `backend/app/db/models/triage.py` | Added `user_reacted_at`, `user_responded_at` fields |
| `backend/app/db/repositories/triage.py` | Added `mark_user_reacted()`, `mark_user_responded()` |
| `backend/app/services/triage_delivery.py` | Added conversation-aware digest methods |
| `backend/app/worker/tasks.py` | Updated `send_digest` with conversation grouping |
| `backend/app/schemas/triage.py` | Added response tracking fields |
| `frontend/src/types/index.ts` | Added `user_reacted_at`, `user_responded_at` |
| `frontend/src/components/triage/SummaryCard.tsx` | Show response status |
| `backend/tests/services/test_digest_grouper.py` | **NEW** - Tests for grouping |
| `backend/tests/services/test_digest_response_checker.py` | **NEW** - Tests for response checking |
| `backend/tests/integration/test_digest_flow.py` | **NEW** - Integration tests for full digest flow |
| `backend/alembic/versions/911eaf99501d_*.py` | Migration for new fields |

## How It Works

1. **Reaction Tracking**: When user reacts to a message in Slack, the `reaction_added` event marks the classification as reacted.

2. **Conversation Grouping**: At digest time, messages are grouped:
   - Same `thread_ts` → one conversation
   - Same DM channel → one conversation
   - Same channel without thread → one conversation (LLM can subdivide)

3. **Response Detection**: Before sending digest:
   - Check if user reacted to any message in conversation
   - Check if `user_responded_at` is set on any message
   - Check if user posted after the last message in conversation
   - Filter out responded conversations

4. **Digest Summary**: Remaining conversations get one summary each, not per-message.

## Status

✅ All Phases Complete
✅ All Tests Passing (37 unit + 10 integration = 47 new tests)
