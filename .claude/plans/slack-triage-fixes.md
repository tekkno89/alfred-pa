# Slack Triage Fixes

## Overview

Multiple issues identified in the Slack triage digest system:

1. **Thinking model token budget** - `gemini-2.5-flash` uses thinking tokens, leaving only ~6 tokens for output with `max_tokens=150`, causing truncated summaries
2. **Wrong Slack token for response checking** - Using bot token instead of user token, causing `not_in_channel` errors when bot isn't in monitored channels
3. **Missing separator** - Need visual separator after "more messages" link
4. **Complex event-driven tracking** - Reaction/response tracking via events is overcomplicated and partially broken

## Root Cause Analysis

### Thinking Model Issue

Gemini 2.5 Flash is a "thinking" model that uses internal reasoning tokens. These count against `max_output_tokens`:
- `max_tokens=150`
- Model uses ~140 thinking tokens
- Only ~6-35 tokens left for actual output
- Results: "Claire," "Caitlin and Paul are" (truncated)

**Solution:** Use `gemini-2.5-flash-lite` (newest non-thinking model)

### Wrong Token Issue

`DigestResponseChecker` uses `SlackService()` which creates a client with the bot token. When checking if user responded to messages in monitored channels, the bot may not be a member, causing API failures.

**Solution:** Use user's OAuth token (already stored encrypted) - they ARE members of their monitored channels.

## Implementation

### Phase 1: Critical Fixes ✅ COMPLETE

#### Task 1.1: Update Model Defaults ✅
- [x] `backend/app/services/triage_delivery.py:617` → `gemini-2.5-flash-lite`
- [x] `backend/app/services/digest_grouper.py:210` → `gemini-2.5-flash-lite`
- [x] `backend/app/services/channel_intelligence.py:283` → `gemini-2.5-flash-lite`
- [x] `backend/app/core/config.py:49` → `gemini-2.5-flash-lite`

#### Task 1.2: Use User Token in DigestResponseChecker ✅
- [x] Modify `digest_response_checker.py`:
  - Accept `db` parameter in `__init__`
  - Add `_get_user_client(user_id)` method to fetch user's OAuth token
  - Update `_check_user_message_response()` to use user client
  - Update `_get_user_messages_after()` to use user client
- [x] Update `triage_delivery.py` to pass `self.db` to checker
- [x] Update tests to use mock db

#### Task 1.3: Add Separator After "More Messages" ✅
- [x] `backend/app/services/triage_delivery.py:729-731` - Add `lines.append("-----")` after the more messages line

#### Task 1.4: Update Documentation ✅
- [x] Add "Slack Token Usage Guidelines" section to `CLAUDE.md`

### Phase 2: Cleanup ✅ COMPLETE

#### Task 2.1: Remove Reaction Event Handler ✅
- [x] Remove `handle_reaction_added_event()` from `slack.py`
- [x] Remove the call to it in the event handler

#### Task 2.2: Remove Repository Methods ✅
- [x] Remove `mark_user_reacted()` from `TriageClassificationRepository`
- [x] Remove `mark_user_responded()` from `TriageClassificationRepository`

#### Task 2.3: Remove DB Columns ✅
- [x] Create Alembic migration to drop `user_reacted_at` and `user_responded_at` from `triage_classifications`
- [x] Update `TriageClassification` model in `db/models/triage.py`
- [x] Update schemas in `schemas/triage.py`

#### Task 2.4: Update DigestGrouper ✅
- [x] Remove `has_user_reacted()` method from `ConversationGroup`
- [x] Remove `has_user_responded()` method from `ConversationGroup`

#### Task 2.5: Simplify DigestResponseChecker ✅
- [x] Remove `mark_responded_messages()` method

## Files Changed

| Phase | File | Changes |
|-------|------|---------|
| 1 | `triage_delivery.py` | Model default, separator |
| 1 | `digest_grouper.py` | Model default |
| 1 | `channel_intelligence.py` | Model default |
| 1 | `config.py` | Model default |
| 1 | `digest_response_checker.py` | Use user token, pass user_id |
| 1 | `tests/services/test_digest_response_checker.py` | Updated for new constructor |
| 1 | `tests/integration/test_digest_flow.py` | Updated for new constructor |
| 1 | `CLAUDE.md` | Token usage docs |
| 2 | `slack.py` | Remove reaction handler |
| 2 | `triage.py` (repo) | Remove mark methods |
| 2 | `triage.py` (model) | Remove columns |
| 2 | `triage.py` (schemas) | Remove fields |
| 2 | `digest_grouper.py` | Remove has_* methods |
| 2 | Migration | Drop columns |
| 2 | `tests/services/test_digest_grouper.py` | Remove has_* tests |

## Verification

After Phase 1:
1. Check logs for reduced `not_in_channel` errors during digest generation
2. Verify digest summaries are complete (not truncated)
3. Verify separator appears in Slack digest messages

After Phase 2:
1. ✅ All tests pass (44 tests)
2. ✅ Migration ran successfully
3. ✅ No reaction events are processed
