# Agent-Driven Triage Architecture Design Spec

## Overview

Replace the current deterministic triage pipeline with an agent-driven architecture where an AI agent with tools classifies messages, gathers context as needed, and decides delivery timing. A separate digest subagent handles summarization and delivery.

**Problem:** The current pipeline classifies messages in a single LLM call without the ability to gather additional context. It relies on deterministic grouping and scheduling that produces poor results: keyword-triggered false P0s, missing conversation context, double-alerting, and weak digest summaries.

**Solution:** A 4-stage pipeline where Stages 1-2 are deterministic (cheap, fast filtering) and Stages 3-4 are agent-driven (context-gathering, classification, summarization).

---

## Current Architecture (What Changes)

### Kept As-Is
- Slack event receiving endpoint (`/events`) with signature verification and event dedup
- Redis-cached monitored channel set for O(1) lookups (`TriageCacheService`)
- `MonitoredChannel` model and per-channel rules/instructions
- `ChannelSourceRule` for per-sender/bot overrides
- User settings model (`TriageUserSettings`)
- Active hours configuration
- Frontend triage page and settings UI (extended, not replaced)
- Focus mode auto-reply logic
- ARQ worker infrastructure

### Replaced
- `TriagePipeline` (one-shot enrich → classify → store) → Triage Agent with tools
- `TriageEnrichmentService` (fixed context gathering) → Agent calls tools as needed
- `TriageClassifier` (single LLM call) → Agent ReAct loop with tools
- `DigestDeliveryOrchestrator` + cron triggers → Delivery Checker (periodic, lightweight)
- `send_digest` worker task (deterministic grouping + LLM summarize) → Digest Subagent
- `DigestGrouper` (deterministic + LLM clustering) → Digest Subagent holistic review
- `DigestScheduler` (deprecated, already) → Removed
- `EscalationDetector` (multi-ping promotion) → Triage Agent handles via `get_queued_messages` tool

### Modified
- `TriageClassification` model → Add `group_id`, `deliver_by`, `last_related_activity_at`, `settled_threshold` fields
- `TriageUserSettings` model → Add P1 timing configuration fields
- Triage setup wizard → Add timing configuration step
- `TriageEventRouter` → Simplified to just queue message references

---

## Pipeline Architecture

```
┌─────────────────────────────────────────────────────────────┐
│ STAGE 1: Receive & Queue                                    │
│ Slack event → ack → enqueue message reference               │
│ (No content stored, just IDs for later Slack API fetch)     │
└────────────────────────┬────────────────────────────────────┘
                         ▼
┌─────────────────────────────────────────────────────────────┐
│ STAGE 2: Pre-filter Worker                                  │
│ Deterministic, no LLM                                       │
│ 1. Is channel monitored by any Alfred user?                 │
│ 2. Is sender/bot ignored by user?                           │
│ 3. Fan out: queue (message, user_id) per applicable user    │
│ Data: Redis-cached monitored channels + ignore lists        │
└────────────────────────┬────────────────────────────────────┘
                         ▼
┌─────────────────────────────────────────────────────────────┐
│ STAGE 3: Triage Agent (per user, per message)               │
│ Agent with tools, classifies message                        │
│ Can fetch thread, channel history, check queued messages    │
│ P0 → alert_now()                                            │
│ P1 → queue_for_digest() with 1hr TTL, 30min settle          │
│ P2 → queue_for_digest() for EOD                             │
│ P3 → queue_for_digest(P3) (stored, not actively delivered)   │
│ Related to queued message? → link_messages() + upgrade TTL  │
└────────────────────────┬────────────────────────────────────┘
                         ▼
┌─────────────────────────────────────────────────────────────┐
│ STAGE 3.5: Delivery Checker (every 2-3 min, deterministic)  │
│ For each user with queued P1 messages:                      │
│   Any groups settled OR past TTL?                           │
│   If yes → batch all ready groups → dispatch digest subagent│
│ EOD time reached? → dispatch digest subagent with all P2    │
└────────────────────────┬────────────────────────────────────┘
                         ▼
┌─────────────────────────────────────────────────────────────┐
│ STAGE 4: Digest Subagent (per user, per batch)              │
│ Receives all ready message groups for user                  │
│ Groups related messages (threads, channel conversations)    │
│ Fetches additional context as needed                        │
│ Summarizes each group                                       │
│ Sends via Slack DM + updates UI                             │
└─────────────────────────────────────────────────────────────┘
```

---

## Stage 1: Receive & Queue

**What stays:** The existing `/events` endpoint in `slack.py` handles signature verification, event deduplication (Redis), and initial filtering (drops bot messages that would cause loops, drops messages without user/channel/text).

**What changes:** Instead of routing to `TriageEventRouter` inline, the handler enqueues a lightweight ARQ job for Stage 2 with only the message reference — no message content is stored.

**ARQ job arguments (message reference only):**
```python
{
    "channel_id": str,
    "channel_type": str,     # "channel", "group", "im", "mpim"
    "sender_slack_id": str,  # Slack user ID of sender
    "message_ts": str,       # Message timestamp (serves as unique ID in Slack)
    "thread_ts": str | None,
    "event_type": str,       # "message" or "app_mention"
    "bot_id": str | None,
    "subtype": str | None,
}
```

**No message content is stored.** When the triage agent needs the actual message text, it fetches it from Slack using `conversations.history(channel=channel_id, oldest=message_ts, inclusive=true, limit=1)`. This avoids storing user message content in the database, addressing data privacy concerns.

**Trade-off:** If the message is deleted from Slack before the agent processes it, it will be lost. This is acceptable — deleted messages don't need triage. Slack's event delivery guarantees the reference arrives; the content is fetched on demand.

**Rate limit note:** `conversations.history` is Tier 3 (50+ requests per minute). At current message volumes this is well within limits.

---

## Stage 2: Pre-filter Worker

A deterministic worker job that runs per raw message. No LLM calls.

### Step 1: Channel Scope Check
```python
# O(1) Redis SET lookup - existing TriageCacheService pattern
if not await triage_cache.is_monitored_channel(channel_id):
    return  # No users monitor this channel, skip
```

### Step 2: Find Applicable Users
```python
# Existing query: MonitoredChannelRepository.get_users_for_channel()
monitored_channels = await mc_repo.get_users_for_channel(channel_id)
```

### Step 3: Per-User Filtering
For each user monitoring this channel:
```python
# Skip if sender is the user themselves
if sender_slack_id == user.slack_user_id:
    continue

# Check per-user ignore rules (ChannelSourceRule with action="ignore")
# Cached in Redis: triage:ignore_rules:{user_id}:{channel_id}
if await is_sender_ignored(user_id, channel_id, sender_slack_id):
    continue

# Check if user has triage enabled (is_always_on or in focus mode)
if not await should_triage(user_id):
    continue

# Enqueue triage agent job
await enqueue_triage_agent(message_id=msg_id, user_id=user_id)
```

### DM Handling

DMs are not "monitored channels" but still need triage. The pre-filter handles DMs separately:

```python
if channel_type in ("im", "mpim"):
    # DM: Find Alfred users who have triage enabled
    # and whose Slack user ID is in the DM channel
    # Use existing authorization list from Slack event to identify recipients
    for auth in event.get("authorizations", []):
        user = await get_alfred_user_by_slack_id(auth["user_id"])
        if user and auth["user_id"] != sender_slack_id:
            if await should_triage(user.id):
                await enqueue_triage_agent(message_id=msg_id, user_id=user.id)
    return
```

DMs skip the monitored channel check and ignore list check. They go directly to the triage agent if the recipient has triage enabled.

### Redis Cache Structure for Pre-filter

| Key | Type | Contents | TTL | Invalidation |
|-----|------|----------|-----|--------------|
| `triage:monitored_channels_set` | SET | All monitored channel IDs | None | Rebuild on channel add/remove |
| `triage:channel_users:{channel_id}` | SET | User IDs monitoring this channel | 5 min | Delete on channel config change |
| `triage:ignore_rules:{user_id}:{channel_id}` | SET | Ignored sender/bot IDs | 5 min | Delete on rule change |
| `triage:user_channel_rules:{user_id}:{channel_id}` | HASH | Channel priority, instructions, summary_behavior | 5 min | Delete on settings change |

Invalidation: When a user updates settings via API, the endpoint deletes the relevant cache keys. Short TTL (5 min) ensures eventual consistency even if invalidation is missed.

---

## Stage 3: Triage Agent

A LangGraph ReAct agent that receives a `(message, user_id)` pair and has tools to gather context, classify, and take action.

### Agent Input
```python
{
    "message_ref": {
        "channel_id": str,
        "message_ts": str,
        "thread_ts": str | None,
        "sender_slack_id": str,
        "event_type": str,
    },
    "user_id": str,
    "user_config": {
        "sensitivity": str,         # low/medium/high
        "custom_rules": str | None, # freeform user rules
        "p0_definition": str | None,
        "p1_definition": str | None,
        "p2_definition": str | None,
        "p3_definition": str | None,
    }
}
```

Note: The agent receives only a message reference, not the text. Its first action is always to call `fetch_message` to retrieve the actual content from Slack, followed by `get_queued_messages` to check for related context.

### Agent System Prompt

The agent's system prompt instructs it to:
1. **Always start** by calling `fetch_message` to get the message text
2. **Always call** `get_queued_messages` next to see what's already classified for this user in this channel
3. Analyze the full message meaning, not just keywords
4. Gather additional context if needed (thread, channel history, channel rules)
5. Check if message is related to any queued messages — if so, call `link_messages`
6. Classify based on what action the user needs to take
7. Take exactly one terminal action

Key classification guidance:
- **P0 (notify_now):** Requires IMMEDIATE action. Active emergencies, explicit urgent requests. NOT status updates, NOT resolved issues, NOT FYI messages.
- **P1 (summarize_next):** Needs attention within hours. Direct asks, time-sensitive questions, requests with a deadline.
- **P2 (summarize_eod):** Notable information for EOD review. Updates, FYIs, discussions, informational content, resolved issues.
- **P3 (ignore):** Defined entirely by the user's own P3 configuration. No hardcoded default. If the user hasn't defined P3 criteria, the agent should not classify anything as P3 — use P2 instead.

Semantic analysis guidance:
- Analyze the FULL message context and meaning, not just keywords
- Consider the actual intent: active situation vs. resolved, action required vs. informational
- Words like "crash", "error", "issue" don't automatically mean urgent
- Look for indicators: "resolved", "fixed", "back up" = informational, not urgent
- Consider tense: "is crashing" (active) vs "was crashing but is fixed" (resolved)
- Classify based on what action the user needs to take, not what topics are mentioned

### Agent Tools

| Tool | Purpose | Limit per message |
|------|---------|-------------------|
| `fetch_message` | Fetch message text from Slack API (agent's first call) | 1 |
| `get_queued_messages` | See what's already queued for this user in this channel (agent's second call) | 1 |
| `fetch_thread` | Get thread messages for context | 2 |
| `fetch_channel_history` | Get recent non-threaded messages in channel | 2 |
| `get_user_channel_rules` | Get user's rules/guidance for this channel (cached) | 1 |
| `alert_now` | Send immediate P0 notification via Slack DM + SSE | 1 |
| `queue_for_digest` | Queue message with priority and delivery parameters | 1 |
| `link_messages` | Link this message to an existing queued message, upgrade priority/TTL | 1 |

**Total tool call limit: 10 per message.** If hit, classify with available info and set `needs_review=true`. Agent notifies user that it couldn't fully investigate.

**Terminal actions (exactly one per invocation):**
- `alert_now(classification)` → Immediate Slack DM + SSE push. Stores `TriageClassification` with `queued_for_digest=False`.
- `queue_for_digest(classification, priority)` → Stores `TriageClassification` with delivery parameters based on priority:
  - P1: `deliver_by = now + 1hr`, `settled_threshold = 30min`, `queued_for_digest=True`
  - P2: `deliver_by = user's EOD time`, `settled_threshold = None`, `queued_for_digest=True`
  - P3: `queued_for_digest=False`, stored for review page only
- `link_messages(new_id, existing_id, new_priority)` → Sets same `group_id` on both messages, upgrades group's `deliver_by` and `settled_threshold` to match higher priority. Must be followed by `queue_for_digest`.

### Tool Details

**`fetch_message(channel_id, message_ts)`**
Fetches a single message's text from Slack. Uses `conversations.history(channel=channel_id, oldest=message_ts, inclusive=true, limit=1)`. Returns `{user, text, ts, thread_ts, permalink}`. This is always the agent's first tool call — it needs the message content before it can classify.

**`fetch_thread(thread_ts, channel_id, limit=10)`**
Returns the last N messages from a thread. Uses Slack API `conversations.replies`. Returns list of `{user, text, ts}`.

**`fetch_channel_history(channel_id, limit=10)`**
Returns the last N non-threaded messages in a channel. Uses Slack API `conversations.history`. Filters out thread replies. Returns list of `{user, text, ts, thread_ts}`.

**`get_user_channel_rules(user_id, channel_id)`**
Returns the user's configuration for this channel from Redis cache (`triage:user_channel_rules:{user_id}:{channel_id}`). Falls back to DB query + cache population. Returns `{priority, triage_instructions, summary_behavior, source_rules: [{entity_id, entity_type, action}]}`.

**`get_queued_messages(user_id, channel_id)`**
Returns messages currently queued for this user in this channel. Query: `TriageClassification` where `user_id=X, channel_id=Y, queued_for_digest=True`. Returns list of `{id, sender_name, abstract, action, group_id, message_ts}`.

**`alert_now(abstract, reason, confidence)`**
Stores classification and sends immediate notification. Uses existing Slack DM sending + SSE push logic from current `_deliver_urgent`.

**`queue_for_digest(abstract, reason, confidence, priority)`**
Stores classification with delivery parameters. Sets `deliver_by`, `settled_threshold`, `last_related_activity_at` based on priority.

**`link_messages(existing_message_id, priority)`**
Links the current message to an existing queued message by assigning the same `group_id`. If the existing message is already in a group, the new message joins that group. Updates the group's delivery parameters to match the highest priority in the group. The current message is then also queued via `queue_for_digest`.

### Error Handling

- **Agent crash / LLM error:** Requeue the `(message, user_id)` job with retry counter incremented. After 3 retries, store as P2 with `needs_review=true`.
- **Tool call limit hit:** Agent classifies with available context. Sets `needs_review=true`. Stores result and continues.
- **Slack API error in tools:** Tool returns error message to agent. Agent can retry or classify without that context.

---

## Stage 3.5: Delivery Checker

A lightweight periodic worker (every 2-3 minutes). No LLM calls. Pure database queries.

```python
async def check_delivery_readiness():
    """Check if any message groups are ready for delivery."""
    
    # Find all users with queued P1 messages
    users_with_p1 = await get_users_with_queued_p1()
    
    for user_id in users_with_p1:
        ready_groups = []
        
        # Get all P1 message groups for this user
        groups = await get_p1_groups(user_id)
        
        for group in groups:
            settled = (now - group.last_related_activity_at) > group.settled_threshold
            expired = now > group.deliver_by
            
            if settled or expired:
                ready_groups.append(group)
        
        if ready_groups:
            # Batch all ready groups into one digest dispatch
            await enqueue_digest_subagent(
                user_id=user_id,
                group_ids=[g.id for g in ready_groups],
                digest_type="p1",
            )
    
    # Check EOD digests
    for user_id in await get_users_at_eod_time():
        p2_messages = await get_queued_p2(user_id)
        p3_count = await count_queued_p3(user_id)
        
        if p2_messages or p3_count > 0:
            await enqueue_digest_subagent(
                user_id=user_id,
                group_ids=None,  # All P2 messages
                digest_type="eod",
                p3_count=p3_count,
            )
```

### Group Tracking

Messages are grouped via `group_id` on `TriageClassification`:
- When the triage agent calls `link_messages`, both messages get the same `group_id`
- Ungrouped messages have `group_id = NULL` (treated as a group of 1)
- A group's delivery parameters are determined by the highest-priority member:
  - `deliver_by`: Earliest `deliver_by` in the group
  - `settled_threshold`: Shortest threshold in the group (from highest priority)
  - `last_related_activity_at`: Latest activity across all group members

---

## Stage 4: Digest Subagent

A LangGraph agent that receives a batch of ready message groups and composes a digest.

### Subagent Input
```python
{
    "user_id": str,
    "digest_type": "p1" | "eod",
    "groups": [
        {
            "group_id": str,
            "messages": [
                {
                    "id": str,
                    "sender_name": str,
                    "channel_name": str,
                    "abstract": str,
                    "action": str,
                    "message_ts": str,
                    "thread_ts": str | None,
                    "slack_permalink": str,
                }
            ]
        }
    ],
    "p3_count": int | None,  # For EOD digests: number of ignored messages
}
```

### Subagent Tools

| Tool | Purpose |
|------|---------|
| `fetch_thread` | Get full thread for better summarization |
| `fetch_channel_history` | Get non-threaded channel messages for conversation context |
| `send_digest_dm` | Send formatted digest to user's Slack DM |
| `save_digest_record` | Persist digest to DB for UI display |
| `mark_delivered` | Update message statuses to delivered |

### Subagent Responsibilities

1. **Review all messages holistically** — Look across groups for additional relationships the triage agent might have missed.

2. **Group related messages** — Within each group and across groups:
   - Same thread → merge together
   - Same channel, related topic (non-threaded) → identify as conversation
   - Use `fetch_channel_history` to understand conversation flow between messages

3. **Summarize selectively** — NOT all messages received are related. The subagent must:
   - Identify which messages are part of the same conversation
   - Messages from the same channel are NOT automatically related — analyze the content
   - Summarize each conversation group independently
   - Do NOT combine unrelated messages into a single summary
   - Include key participants, topic, and any action items per group

4. **Format digest** — Order by priority (P1 first, then P2). Include:
   - Conversation summaries with Slack permalinks
   - Participant names
   - For EOD: Footer with P3 count and link to review page

5. **Deliver** — Send via Slack DM using `send_digest_dm`, then persist records and mark delivered.

### EOD Digest Footer
```
---
12 messages were auto-ignored today. [Review them →](https://alfred.example.com/triage?filter=ignored)
```

---

## Data Model Changes

### No New Tables

Message content is not stored. Message references are passed as ARQ job arguments and message text is fetched from Slack API on demand. The existing `TriageClassification` table stores only the AI-generated `abstract` (summary), not raw message content.

### Modified: `triage_classifications`

New columns:
```sql
ALTER TABLE triage_classifications ADD COLUMN group_id UUID;
ALTER TABLE triage_classifications ADD COLUMN deliver_by TIMESTAMPTZ;
ALTER TABLE triage_classifications ADD COLUMN last_related_activity_at TIMESTAMPTZ;
ALTER TABLE triage_classifications ADD COLUMN settled_threshold INTEGER;  -- minutes
ALTER TABLE triage_classifications ADD COLUMN needs_review BOOLEAN DEFAULT FALSE;
ALTER TABLE triage_classifications ADD COLUMN retry_count INTEGER DEFAULT 0;

CREATE INDEX idx_tc_group_id ON triage_classifications(group_id) WHERE group_id IS NOT NULL;
CREATE INDEX idx_tc_delivery ON triage_classifications(user_id, deliver_by) 
    WHERE queued_for_digest = TRUE AND deliver_by IS NOT NULL;
```

### Modified: `triage_user_settings`

New columns:
```sql
ALTER TABLE triage_user_settings ADD COLUMN p1_max_wait_minutes INTEGER DEFAULT 60;
ALTER TABLE triage_user_settings ADD COLUMN p1_settled_threshold_minutes INTEGER DEFAULT 30;
```

P2 timing is controlled by the existing `eod_review_time` field. P3 messages are not actively delivered.

---

## User Configuration

### Settings Page Additions

New section in triage settings for P1 delivery timing:
- **P1 max wait time** (default: 60 minutes) — "How long to wait before sending a P1 digest, even if conversations are still active"
- **P1 settle threshold** (default: 30 minutes) — "How long to wait after the last message in a conversation before considering it settled"

### Setup Wizard Addition

New step in the triage setup wizard after channel selection:
1. Brief explanation: "Alfred batches non-urgent messages into digests instead of interrupting you for every message."
2. Configure P1 timing (with defaults pre-filled)
3. Confirm EOD review time (existing, carried forward)

---

## Migration Strategy

This is a significant architectural change. It should be implemented incrementally:

### Phase A: Infrastructure
- Add new columns to `triage_classifications` and `triage_user_settings`
- Set up Redis cache structures for pre-filter
- Build cache invalidation on settings update endpoints

### Phase B: Receive & Pre-filter (Stages 1-2)
- Modify Slack event handler to enqueue message references (no content stored)
- Build pre-filter worker
- Verify: messages get correctly fanned out to per-user queues
- Run in parallel with existing pipeline (dual-write) for validation

### Phase C: Triage Agent (Stage 3)
- Build triage agent with LangGraph + tools
- Wire up to pre-filter output
- Verify: classifications match or exceed current quality
- Switch from old pipeline to new agent (feature flag)

### Phase D: Delivery Checker + Digest Subagent (Stages 3.5-4)
- Build delivery checker
- Build digest subagent with LangGraph + tools
- Wire up to triage agent output
- Verify: digests are well-grouped and well-timed
- Disable old digest orchestrator

### Phase E: Cleanup
- Remove deprecated code: `TriagePipeline`, `TriageEnrichmentService`, `TriageClassifier`, `DigestDeliveryOrchestrator`, `DigestScheduler`, `DigestGrouper`, `EscalationDetector`
- Remove old cron jobs
- Update documentation and diagrams

Each phase is independently deployable. Phase B can run alongside the existing pipeline for validation before switching over.

---

## What This Does NOT Change

- **Alfred chat agent** — The conversational AI assistant is unchanged. Only the triage/digest pipeline is replaced.
- **Focus mode** — Focus mode auto-replies and session management stay the same. The triage agent respects focus session context.
- **Frontend triage page** — The UI reads from `triage_classifications` and `conversation_summaries` tables, which are still populated (by the new agents instead of the old pipeline).
- **Feedback/learning system** — `TriageFeedback`, `FeedbackEmbedding`, `SenderActionDistribution`, `TopicAffinity` tables and their associated services continue to work. The triage agent can use learned signals as tool inputs in future iterations.
