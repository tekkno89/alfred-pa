# Unified Conversation Summaries Implementation Plan

## Problem Statement

Digests show different grouping in Slack vs UI:
- **Slack DM**: Messages grouped into conversations (threads, DMs, channels)
- **UI**: Individual ungrouped messages

This happens because grouping is done in-memory during digest creation but not persisted.

## Solution

Persist conversation groupings as first-class entities, so both Slack and UI query the same data.

---

## Data Model

### New Table: `conversation_summaries`

```sql
CREATE TABLE conversation_summaries (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id),
    
    -- Conversation identification
    conversation_type VARCHAR(20) NOT NULL,  -- 'thread', 'dm', 'channel'
    channel_id VARCHAR(50) NOT NULL,
    channel_name VARCHAR(255),
    thread_ts VARCHAR(50),  -- NULL for channel/DM messages
    
    -- Summary content (generated once at digest time)
    abstract TEXT NOT NULL,
    participants JSONB,  -- [{"slack_id": "U123", "name": "Alice"}, ...]
    message_count INTEGER NOT NULL,
    priority_level VARCHAR(20) NOT NULL,  -- highest among messages (p0, p1, p2, p3)
    
    -- For Slack link (oldest message in conversation)
    first_message_ts VARCHAR(50) NOT NULL,
    slack_permalink TEXT,
    
    -- Link to parent digest
    digest_summary_id UUID REFERENCES triage_classifications(id),
    
    -- Timestamps
    first_message_at TIMESTAMPTZ,
    last_message_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    
    -- Status tracking (independent of digest review)
    reviewed_at TIMESTAMPTZ,
    user_reacted_at TIMESTAMPTZ,
    user_responded_at TIMESTAMPTZ
);

-- Indexes
CREATE INDEX idx_cs_user_digest ON conversation_summaries(user_id, digest_summary_id);
CREATE INDEX idx_cs_thread ON conversation_summaries(channel_id, thread_ts);
CREATE INDEX idx_cs_user_created ON conversation_summaries(user_id, created_at DESC);
CREATE INDEX idx_cs_digest_summary ON conversation_summaries(digest_summary_id);
```

### Modified Table: `triage_classifications`

```sql
ALTER TABLE triage_classifications 
ADD COLUMN conversation_summary_id UUID REFERENCES conversation_summaries(id);

CREATE INDEX idx_tc_conversation_summary_id ON triage_classifications(conversation_summary_id);

-- Note: digest_summary_id will be removed from individual messages
-- (moved to conversation_summaries.digest_summary_id)
-- Migration handles this transition
```

### Relationship Hierarchy

```
digest_summary (triage_classification with priority=digest_summary)
    │
    └── conversation_summaries (1 or more)
            │
            └── triage_classifications (1 or more individual messages)
```

---

## Implementation Tasks

### Phase 1: Database Schema

- [ ] Create Alembic migration for `conversation_summaries` table
- [ ] Add `conversation_summary_id` column to `triage_classifications`
- [ ] Add all indexes
- [ ] Test migration on local dev environment

### Phase 2: Backend Models & Repositories

- [ ] Create `backend/app/db/models/conversation_summary.py`
  - SQLAlchemy model matching schema above
  - Relationships to user, digest_summary, triage_classifications

- [ ] Create `backend/app/db/repositories/conversation_summary_repository.py`
  - `create(summary: ConversationSummary) -> ConversationSummary`
  - `get_by_digest(digest_id: str) -> list[ConversationSummary]`
  - `get_with_messages(summary_id: str) -> ConversationSummary`
  - `get_recent_thread_summary(thread_ts: str, user_id: str, days: int) -> ConversationSummary | None`

- [ ] Update `backend/app/db/models/triage.py`
  - Add `conversation_summary` relationship
  - Add `conversation_summary_id` column

### Phase 3: Backend Service Layer

- [ ] Modify `backend/app/services/digest_grouper.py`
  - `group_messages_with_context()` now persists each `ConversationGroup` as `ConversationSummary`
  - Link child messages via `conversation_summary_id`
  - Clear `digest_summary_id` from child messages (now on conversation_summary)
  - Return persisted `ConversationSummary` objects

- [ ] Modify `backend/app/services/triage_delivery.py`
  - `send_conversation_digest_dm()` - query persisted conversations by `digest_summary_id`
  - `send_end_of_day_digest_dm()` - same pattern
  - `create_scheduled_digest_summary()` - link conversations via `digest_summary_id`
  - `create_conversation_summary()` - use persisted summary instead of generating on-the-fly

- [ ] Modify `backend/app/services/triage_delivery.py`
  - `create_conversation_summary()` - check for recent thread summary to include context
  - Abstract generation prompt: "Earlier conversation about X - follow-up on Y"

### Phase 4: Backend API Endpoints

- [ ] Add to `backend/app/api/triage.py`:
  - `GET /digests/{digest_id}/conversations` - list conversations in a digest
    - Query params: `limit`, `offset`, `priority` (filter)
    - Returns: `ConversationSummaryList` with pagination
  
  - `GET /conversations/{conversation_id}` - single conversation with metadata
  
  - `GET /conversations/{conversation_id}/messages` - messages in a conversation
    - Query params: `limit`, `offset`
    - Returns: paginated list of `TriageClassification`

- [ ] Create schemas in `backend/app/schemas/triage.py`:
  - `ConversationSummaryResponse`
  - `ConversationSummaryList`
  - `ConversationMessageList`

### Phase 5: Frontend Hooks

- [ ] Create `frontend/src/hooks/useConversations.ts`
  ```typescript
  // Fetch conversations for a digest
  export function useDigestConversations(digestId: string | null, options?: { priority?: string }) {}
  
  // Fetch single conversation
  export function useConversation(conversationId: string | null) {}
  
  // Fetch messages in a conversation
  export function useConversationMessages(conversationId: string | null) {}
  ```

- [ ] Add React Query cache invalidation for hierarchy:
  - Invalidation of digest → invalidates conversations
  - Invalidation of conversation → invalidates messages

### Phase 6: Frontend Components

- [ ] Create `frontend/src/components/triage/ConversationSummaryCard.tsx`
  - Props: `conversation: ConversationSummary`, `onMarkReviewed`, `expanded`
  - Shows conversation type icon (thread/dm/channel)
  - Priority-specific clock icon (P1=orange, P2=yellow, P3=blue)
  - Channel name, participant names, message count
  - Abstract (truncated when collapsed)
  - Expandable to show individual messages
  - "View on Slack" link (to oldest message)

- [ ] Modify `frontend/src/components/triage/SummaryCard.tsx`
  - Fetch conversations via `useDigestConversations(digest.id)`
  - Render list of `ConversationSummaryCard` components
  - Group by priority (P1 section, P2 section, P3 section)
  - Remove old flat child message list

- [ ] Update `frontend/src/components/triage/ChildMessageItem.tsx` (if needed)
  - Used inside expanded conversation
  - Keep existing "Correct Classification" functionality

### Phase 7: Priority Icons

- [ ] Add to `frontend/src/components/triage/ConversationSummaryCard.tsx`:
  ```typescript
  const PRIORITY_ICONS: Record<string, { icon: typeof Clock; className: string; bgClassName: string }> = {
    p1: { 
      icon: Clock, 
      className: 'text-orange-500',
      bgClassName: 'bg-orange-100 dark:bg-orange-900/40'
    },
    p2: { 
      icon: Clock, 
      className: 'text-yellow-500',
      bgClassName: 'bg-yellow-100 dark:bg-yellow-900/40'
    },
    p3: { 
      icon: Clock, 
      className: 'text-blue-500',
      bgClassName: 'bg-blue-100 dark:bg-blue-900/40'
    },
  }
  ```

### Phase 8: Dashboard Card Improvements

- [ ] Modify `frontend/src/components/dashboard/TriageCard.tsx`:
  - Add `max-h-80` to CardContent for scrolling
  - Fetch `useClassifications({ limit: 10 })` (increase from 5)
  - Show "X more" link at bottom when `total > 10`
  - Link to `/triage` for full view

### Phase 9: Migration Script

- [ ] Create migration for existing `digest_summary` records:
  ```python
  # Pseudocode:
  # 1. For each triage_classification where priority_level=digest_summary:
  # 2.   Get all child messages (where digest_summary_id = summary.id)
  # 3.   Group children by (channel_id, thread_ts)
  # 4.   For each group:
  # 5.     Create conversation_summary
  # 6.     Update children's conversation_summary_id
  # 7.     Clear children's digest_summary_id
  ```

- [ ] Handle edge cases:
  - Empty digests (no children)
  - Orphaned children (summary deleted)
  - Large digests (batch processing)

### Phase 10: Testing

- [ ] Backend unit tests:
  - `tests/test_digest_grouper.py` - grouping + persistence
  - `tests/test_conversation_summary_repository.py` - CRUD operations
  - `tests/api/test_conversations.py` - new endpoints

- [ ] Backend integration tests:
  - Full digest flow: classify → group → persist → API → Slack
  - New replies after digest: creates new conversation_summary

- [ ] Frontend tests:
  - `ConversationSummaryCard` rendering
  - `useConversations` hooks
  - Cache invalidation

---

## Edge Cases & Behavior

### Single Message (Not in Thread)

Creates `conversation_summary` with:
- `conversation_type = 'dm'` or `'channel'`
- `message_count = 1`
- `thread_ts = NULL`

No special handling needed - treated same as multi-message conversations.

### Mixed Priority Messages in Thread

The `conversation_summary.priority_level` = highest priority among all messages in the thread.

Abstract generation highlights the higher-priority message:
> "Urgent: CEO asking for pricing response. Discussion of competitor strategy and team debate."

### New Replies After Digest Sent

New messages are classified and queued for next digest. When next digest runs:
1. Creates NEW `conversation_summary` for same `thread_ts`
2. Abstract generation checks for recent summary:
   ```python
   recent = await repo.get_recent_thread_summary(thread_ts, user_id, days=7)
   if recent:
       prompt_context = f"Earlier conversation: {recent.abstract}"
   ```
3. LLM generates contextual abstract:
   > "Related to earlier conversation about pricing - follow-up on action items assigned to product team."

### Message Deletion from Slack

- `slack_permalink` may 404 - UI handles gracefully
- Abstract and message content already stored at classification time
- No impact on conversation_summary

### Review Semantics

Each level is independent:
- **Digest reviewed**: User has seen the digest
- **Conversation reviewed**: User has handled the conversation (optional)
- **Message**: No review action - "Correct Classification" for feedback

No cascade needed.

---

## API Specification

### GET /api/triage/digests/{digest_id}/conversations

List conversations in a digest.

**Query Parameters:**
- `limit` (int, default 20, max 100)
- `offset` (int, default 0)
- `priority` (string, optional) - filter by 'p1', 'p2', 'p3'

**Response:**
```json
{
  "items": [
    {
      "id": "uuid",
      "conversation_type": "thread",
      "channel_id": "C123",
      "channel_name": "competitive-intel",
      "thread_ts": "1234567890.123456",
      "abstract": "Discussion about competitor pricing...",
      "participants": [
        {"slack_id": "U123", "name": "Alice"},
        {"slack_id": "U456", "name": "Bob"}
      ],
      "message_count": 20,
      "priority_level": "p1",
      "first_message_ts": "1234567890.123456",
      "slack_permalink": "https://...",
      "first_message_at": "2026-04-30T16:32:00Z",
      "last_message_at": "2026-04-30T18:45:00Z",
      "created_at": "2026-04-30T17:00:00Z",
      "reviewed_at": null
    }
  ],
  "total": 42,
  "limit": 20,
  "offset": 0
}
```

### GET /api/triage/conversations/{conversation_id}

Get single conversation with full metadata.

**Response:** Single `ConversationSummaryResponse`

### GET /api/triage/conversations/{conversation_id}/messages

Get messages in a conversation.

**Query Parameters:**
- `limit` (int, default 50, max 200)
- `offset` (int, default 0)

**Response:**
```json
{
  "items": [
    {
      "id": "uuid",
      "sender_name": "Alice",
      "sender_slack_id": "U123",
      "abstract": "Just saw competitor announced 15% price cut",
      "message_ts": "1234567890.123456",
      "slack_permalink": "https://...",
      "priority_level": "p1",
      "created_at": "2026-04-30T16:32:00Z"
    }
  ],
  "total": 20,
  "limit": 50,
  "offset": 0
}
```

---

## File Changes Summary

### New Files
- `backend/app/db/models/conversation_summary.py`
- `backend/app/db/repositories/conversation_summary_repository.py`
- `backend/alembic/versions/XXX_add_conversation_summaries.py`
- `backend/alembic/versions/XXX_migrate_existing_digests.py`
- `frontend/src/components/triage/ConversationSummaryCard.tsx`
- `frontend/src/hooks/useConversations.ts`
- `backend/tests/test_conversation_summary_repository.py`
- `backend/tests/api/test_conversations.py`

### Modified Files
- `backend/app/db/models/triage.py` - add conversation_summary_id
- `backend/app/db/repositories/triage.py` - add conversation_summary queries
- `backend/app/services/digest_grouper.py` - persist conversations
- `backend/app/services/triage_delivery.py` - query persisted conversations
- `backend/app/api/triage.py` - new endpoints
- `backend/app/schemas/triage.py` - new schemas
- `frontend/src/components/triage/SummaryCard.tsx` - render conversations
- `frontend/src/components/dashboard/TriageCard.tsx` - max-height, "X more" link

---

## Rollout Plan

1. **Deploy database migration** (conversation_summaries table + column)
2. **Deploy backend changes** (models, repos, services, APIs)
3. **Deploy frontend changes** (components, hooks)
4. **Run migration script** for existing digests (can be async)
5. **Monitor** for issues, rollback if needed

---

## Success Criteria

- [ ] Slack DM and UI show identical conversation groupings
- [ ] Expanding a conversation shows individual messages
- [ ] Priority icons display correctly (orange/yellow/blue clock)
- [ ] Dashboard card respects max-height and shows "X more" link
- [ ] New replies after digest create contextual abstract
- [ ] Existing digests migrated successfully
- [ ] All tests pass
