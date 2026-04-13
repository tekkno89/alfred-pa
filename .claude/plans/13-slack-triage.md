# PRD: Alfred Slack Triage System

**Author:** [Your Name]
**Date:** March 21, 2026
**Status:** Draft
**Version:** 2.0

---

## 1. Overview

### 1.1 Problem statement

Alfred users frequently break focus to check Slack because they fear missing important messages. Even with focus mode enabled, the anxiety persists — the auto-reply and bypass button address the symptom (someone needs you now) but not the root cause (you don't know what's accumulating while you're away). Additionally, important messages in team channels (e.g., outage reports in #support) can go unnoticed when users aren't actively monitoring those channels.

### 1.2 Proposed solution

Build a Slack triage system that passively monitors incoming DMs, @mentions, and user-selected channels on behalf of each Alfred user. An LLM-powered classifier evaluates every incoming message for urgency and relevance, categorizing it into one of four priority levels: P0 (urgent/immediate), P1 (high), P2 (medium), or P3 (low). This gives users confidence that nothing critical will slip through, reducing the compulsion to check Slack manually.

### 1.3 Scope

**In scope:**
- Slack message triage classifier (DMs to Alfred users, @mentions of Alfred users, and monitored channel messages)
- User-configurable monitored channels with priority levels and per-channel triage instructions
- Four-tier classification: P0 (urgent), P1 (high), P2 (medium), P3 (low), plus "review" for uncertain cases
- Customizable digest cadence per priority level (intervals, active hours, specific times)
- Per-priority alert toggles and deduplication windows
- Post-focus session digest delivered via Alfred Slack bot DM with Slack deep links
- Scheduled digests delivered at configurable times (P1/P2 at intervals, P3 daily summary)
- Zero message persistence — raw Slack message text is never stored in the database
- Multi-tenant isolation — all triage state scoped per user with no cross-tenant data leakage
- Integration with existing focus mode, Pomodoro, VIP list, and bypass notification features
- Redis-backed job queue for triage processing using existing ARQ infrastructure
- Comprehensive debug and test logging throughout the pipeline
- Slack response time analytics
- Priority calibration system with sampled messages for user rating
- AI-powered Triage Wizard for generating custom priority definitions

**Out of scope (future PRDs):**
- Proactive investigation agent (Datadog, logs, infrastructure checks)
- External event bus consumers (Raspberry Pi, MQTT, smart home integrations)
- Calendar-aware auto-focus
- Slack OAuth scope changes beyond what's needed for channel monitoring

### 1.4 Success criteria

- Users report reduced frequency of manually checking Slack during focus sessions
- Urgent messages are classified and surfaced within 5 seconds of receipt
- Zero raw Slack message text persisted in any database table or log output
- Triage pipeline handles sustained throughput of 50+ messages/minute per user without degradation
- Existing focus mode auto-reply and bypass button functionality is unaffected

---

## 2. Architecture

### 2.1 High-level flow

```
Slack Event (HTTP webhook)
  │
  ├─ Existing flow (unchanged):
  │    DM to Alfred user in focus → auto-reply via bot + bypass button
  │
  └─ New flow (parallel):
       │
       ▼
  Pre-filter: is this a monitored channel? Is sender excluded?
       │ (Redis SET check — O(1), sub-millisecond)
       │
       ▼
  Route by user_id(s) → per-user triage job enqueued (ARQ/Redis)
       │
       ▼
  Enrichment (in-memory)
       │ - Gather channel priority, triage instructions
       │ - Load user's custom P0-P3 definitions
       │ - Summarize thread/DM context for classification
       │ - Check VIP status, focus session state
       ▼
  Triage classifier (LLM call)
       │
       ├─ P0 (urgent) → Immediate Slack DM + SSE banner + notification sound
       │                 (deduplicated within configurable window)
       ├─ P1 (high) → Queue for scheduled digest (configurable interval)
       ├─ P2 (medium) → Queue for scheduled digest (configurable interval)
       ├─ P3 (low) → Queue for daily summary
       └─ review → Show in "Needs Attention" filter for manual review
```

### 2.2 Zero message persistence

This is a hard architectural constraint. Raw Slack message text must never be written to PostgreSQL, Redis persistence layers, or application log files.

**What is stored (PostgreSQL):**
- Triage classification records: `user_id`, `sender_slack_id`, `channel_id`, `urgency_level`, `classification_reason` (LLM-generated one-line abstract), `slack_permalink`, `timestamp`, `focus_session_id`
- User configuration: monitored channels, keyword rules, source exclusions, VIP lists, notification preferences
- Analytics: aggregated response pattern data (no message content)

**What is never stored:**
- Raw message text from Slack events
- Message attachments or file references
- Thread content or conversation history
- Any Slack data belonging to users other than the Alfred user being triaged

**Transient processing:**
- Message text exists only in memory during the ARQ job execution
- The LLM classification call receives the message text, produces a classification + one-line abstract, and the original text is discarded
- Redis is used only as a job queue and ephemeral cache (TTL-bounded), not as durable message storage
- ARQ job payloads containing message text must have Redis key expiry set (max 5 minutes)

**Logging constraint:**
- Application logs must never contain raw Slack message text
- Log entries for triage events should reference `slack_message_ts` and `channel_id` for debugging, never the content
- A dedicated `triage_debug` logger (see Section 9) handles pipeline observability without content leakage

### 2.3 Multi-tenant isolation

Alfred supports multiple users, each with their own Slack identity, channel subscriptions, VIP lists, and triage configuration. Isolation requirements:

- Every database table in the triage system includes a `user_id` foreign key
- Every database query is scoped by `user_id` — no unscoped queries permitted
- When a message arrives in a shared channel (e.g., #support), the event handler fans out: it looks up all Alfred users who monitor that channel and enqueues a separate triage job for each user
- Each user's triage job runs with that user's configuration (VIP list, urgency thresholds, keyword rules) — no shared state between users' triage executions
- Slack API calls for enrichment (e.g., user profile lookups) use a shared Redis cache keyed by Slack workspace to avoid redundant API calls, but triage classification is always per-user
- The sender behavioral model (response patterns, interaction frequency) is computed and stored per Alfred user

### 2.4 Queuing strategy

The triage system uses the existing ARQ + Redis infrastructure with the following adjustments:

**Dedicated triage queue:** A separate ARQ queue name (e.g., `triage`) isolates triage jobs from other background tasks (existing agent processing, webhook delivery, etc.). This prevents a burst of Slack messages from starving other job types.

**Job structure:**
```
Queue: triage
Job payload: {
  user_id: UUID,
  slack_event_type: "message_dm" | "app_mention" | "message_channel",
  channel_id: str,
  sender_slack_id: str,
  message_ts: str,
  thread_ts: str | null,
  message_text: str,        # Transient — discarded after classification
  is_thread_reply: bool,
  received_at: datetime
}
```

**Ordering guarantees:** ARQ processes jobs sequentially per worker. A single dedicated triage worker provides FIFO ordering per Alfred instance. If throughput requires scaling, multiple workers can process in parallel — message ordering across workers is not required since each triage classification is independent.

**Redis key TTL:** All ARQ job payloads containing message text must expire within 5 minutes. This ensures that even if a job fails and is not processed, the message text does not persist in Redis.

---

## 3. Slack event handling

### 3.1 Event sources and user mapping

Alfred's triage system monitors Slack on behalf of each **Alfred user** (the human), not the bot. Events arrive via the existing HTTP webhook endpoint (`/api/slack/events`). The system needs to identify which Alfred user(s) each event is relevant to.

| Slack event | What it represents | How to identify the target Alfred user |
|---|---|---|
| Incoming DM to an Alfred user | Another Slack user sends a direct message to someone who has an Alfred account | Map the DM recipient's Slack user ID to an Alfred user via the existing account linking table |
| @mention of an Alfred user in a channel | Someone mentions an Alfred user by name in a channel message | Extract mentioned user IDs from the Slack event payload → look up linked Alfred accounts |
| Message in a monitored channel | Any message posted in a channel that one or more Alfred users have configured for monitoring | Look up all Alfred users who have this `channel_id` in their `monitored_channels` list |

**Important distinction:** The Slack bot is the delivery mechanism (it receives webhook events and sends DMs on behalf of Alfred). But the triage system is watching for messages *relevant to the human user*, not messages directed at the bot. A DM from a coworker to the Alfred user is triaged. A slash command sent to the bot is not.

### 3.2 Event routing

When a Slack event arrives:

1. **Acknowledge immediately** (existing behavior, unchanged — return 200 within 3 seconds)
2. **Pre-filter (fast path):**
   - If the event is a channel message: check the Redis `monitored_channels_set` (see Section 3.5). If the channel is not in the set, skip triage entirely — no DB query, no ARQ job.
   - If the sender is a bot/app: check against global and per-channel exclusion rules (see Section 3.6). If excluded, skip.
   - If the event is a DM or @mention: identify the target Alfred user via account linking.
3. **Identify target Alfred user(s):**
   - For DMs: the Alfred user linked to the recipient Slack user ID
   - For @mentions: each Alfred user whose Slack ID appears in the mention list
   - For channel messages: query `monitored_channels` for all Alfred users who monitor this channel (use the Redis set as a first-pass gate, then query DB for the specific users and their configurations)
4. **Check if triage is active for each user:**
   - If the user is in focus mode → always triage
   - If the user has always-on triage enabled → always triage
   - Otherwise → skip triage for this user
5. **Enqueue triage job** for each eligible user (separate ARQ jobs, each scoped to one `user_id`)
6. **Run existing focus mode logic** in parallel (auto-reply DM, bypass button) — this flow is completely unchanged

### 3.3 Preserving existing focus mode behavior

The existing focus mode DM flow must remain completely intact:

- When a non-VIP user DMs an Alfred user in focus mode, Alfred still sends the auto-reply message with the "Urgent — Notify Them" bypass button
- When the bypass button is clicked, Alfred still fires the existing `focus_bypass` webhook event and triggers the notification (looping alert, flashing tab, banner)
- The triage system runs as a parallel, non-blocking flow — it classifies the same message independently
- If a bypass is triggered, the triage system should mark the corresponding classification record with `escalated_by_sender = true` so the digest summary reflects that the user was already notified

### 3.4 Slack event subscriptions and scopes

Alfred uses **Subscribe to events on behalf of users** (user event subscriptions) in the Slack app configuration. This means the bot receives message events from channels that the *linked Slack user* is a member of — the bot itself does not need to be added to every monitored channel.

**Implications:**
- The available channels for monitoring are the channels each Alfred user's linked Slack account is a member of
- No bot channel membership management is needed
- The Slack app must have the appropriate user token scopes granted during the OAuth flow

**Required user token scopes** (granted during Slack OAuth, in addition to existing scopes):

| Scope | Purpose | Status |
|---|---|---|
| `channels:history` | Read messages in public channels the user is in | Verify if already granted |
| `groups:history` | Read messages in private channels the user is in | Verify if already granted |
| `channels:read` | List public channels for the monitored channel picker | Verify if already granted |
| `groups:read` | List private channels for the monitored channel picker | Verify if already granted |
| `im:history` | Read DM messages | Already configured |
| `users:read` | Look up user info for sender enrichment | Already configured |

**Required bot token scopes** (for sending triage notifications):

| Scope | Purpose | Status |
|---|---|---|
| `chat:write` | Send DM notifications (digest, break summaries, urgent alerts) | Already configured |
| `im:write` | Open DM channels with users for notification delivery | Verify if already granted |

### 3.5 Redis monitored channel set (fast path filter)

To avoid unnecessary database queries on every channel message event, maintain a Redis SET containing all monitored channel IDs across all Alfred users:

```
Key: monitored_channels_set
Type: SET
Members: [channel_id_1, channel_id_2, ...]
```

**Lifecycle:**
- Populated on application startup by querying all active `monitored_channels` records
- Updated via cache invalidation whenever any user adds or removes a monitored channel (`SADD` / `SREM`)
- On cold Redis start (e.g., after Redis restart), the set is rebuilt from the database on the first channel message event or via a startup task

**Lookup flow:**
1. Channel message event arrives
2. `SISMEMBER monitored_channels_set {channel_id}` — O(1)
3. If not in set → check DB as a fallback safety net (handles race conditions during cache rebuilds). If still not found, skip triage.
4. If in set → query DB for the specific Alfred users who monitor this channel and their configurations

This ensures that the vast majority of channel messages (those in unmonitored channels) are discarded in sub-millisecond time with zero database load.

### 3.6 Source exclusions (bot and app filtering)

Many channels have integration bots (Jira, GitHub, PagerDuty, deploy notifications, etc.) that post frequent automated messages. Processing these through the LLM classifier wastes resources and produces low-value classifications.

**Global default behavior:**
- Messages with `bot_id` present in the Slack event payload or with `subtype: "bot_message"` are skipped by default
- This is a pre-filter that runs before ARQ job enqueue — no resources spent on bot messages

**Per-channel overrides:**
- Users can opt specific bots *in* for a monitored channel (e.g., "I want to see PagerDuty alerts in #support but not Jira updates")
- Users can also add specific non-bot Slack user IDs to an exclusion list per channel

**Data model:**

| Column | Type | Description |
|---|---|---|
| `id` | UUID | Primary key |
| `monitored_channel_id` | UUID | Foreign key to monitored_channels |
| `user_id` | UUID | Foreign key to users |
| `slack_entity_id` | VARCHAR | Slack user ID or bot ID to exclude/include |
| `entity_type` | ENUM | `bot` / `user` |
| `action` | ENUM | `exclude` / `include` |
| `display_name` | VARCHAR | Human-readable name for the UI |
| `created_at` | TIMESTAMP | |

**Filtering logic (applied before ARQ enqueue):**
1. If sender has `bot_id` → check if any Alfred user monitoring this channel has an explicit `include` rule for this bot. If no include rule exists → skip.
2. If sender is a regular user → check if any Alfred user monitoring this channel has an `exclude` rule for this user. If excluded → skip for that user only.

---

## 4. Message collector (in-memory enrichment)

### 4.1 Purpose

The message collector transforms a raw Slack event into an enriched triage payload by attaching metadata from multiple sources. All enrichment happens in memory within the ARQ job — no intermediate state is persisted.

### 4.2 Enrichment fields

**From Slack event (direct):**
- `message_text` — the raw message content (transient, discarded after classification)
- `channel_id`, `channel_name`, `channel_type` (DM / public / private)
- `sender_slack_id`, `message_ts`, `thread_ts`
- `is_thread_reply` — whether this message is a reply in a thread
- `slack_permalink` — generated from workspace domain, channel_id, and message_ts

**From sender profile (cached in Redis, TTL 1 hour):**
- `sender_display_name`, `sender_real_name`
- `is_vip` — looked up from the user's VIP list in PostgreSQL

**From behavioral model (precomputed, stored in PostgreSQL per Alfred user):**
- `sender_response_pattern` — enum: `fast_responder` | `normal` | `slow_responder`
- `interaction_frequency` — enum: `high` | `medium` | `low`
- These are computed from Slack conversation history (see Section 8: Analytics)

**From thread context (Slack API call, only if `thread_ts` is present):**
- `thread_participant_count`
- `user_participated_in_thread` — whether the Alfred user has replied in this thread
- `mentions_user_directly` — whether the message @mentions the Alfred user

**From focus session (PostgreSQL):**
- `focus_session_id` — current active focus session, if any
- `focus_minutes_remaining`
- `current_pomodoro_phase` — `work` | `break` | `null`

**From channel configuration (PostgreSQL, cached in Redis per focus session):**
- `channel_priority` — the priority level the user assigned to this channel
- `channel_keyword_rules` — keyword patterns configured for this channel

### 4.3 Caching strategy

To minimize Slack API calls and database queries during high message volume:

| Data | Cache location | TTL | Invalidation |
|---|---|---|---|
| Slack user profiles | Redis | 1 hour | None (stale OK) |
| Alfred user VIP list | Redis | 5 minutes | On VIP list change |
| Monitored channel config | Redis | Duration of focus session | On config change or session end |
| Sender behavioral model | PostgreSQL (precomputed) | Recomputed daily | Manual refresh available |
| Focus session state | Redis | Duration of focus session | On session state change |

---

## 5. Triage classifier

### 5.1 Classification model

The classifier is a single LLM call that receives the enriched triage payload and outputs a structured classification. The LLM provider and model are configurable per deployment (provider-agnostic).

**Input:** The enriched triage payload (Section 4.2), formatted as a structured prompt.

**Output:**
```json
{
  "priority": "p0" | "p1" | "p2" | "p3" | "review",
  "confidence": 0.0-1.0,
  "reason": "Brief explanation of classification (1-2 sentences)",
  "abstract": "One-line summary of the message for digest display"
}
```

**Key design decisions:**
- The `abstract` field is what gets stored — it's the LLM's summary of the message, not the message itself. This preserves the zero-persistence guarantee while giving users useful context in the digest.
- The `reason` field is stored for debugging and analytics. It explains *why* the classifier made this decision.
- A cheap/fast model should be used for classification (sub-2-second response time target).
- Priority levels P0-P3 are user-customizable via the Triage Wizard or manual settings.

### 5.2 Two classification paths

**DM triage path** (for DMs to Alfred users and @mentions of Alfred users):

The primary question: "Is this person trying to reach me about something that can't wait?"

Signals weighted heavily:
- `is_vip` — VIP senders default to `urgent` unless the content is clearly low-priority
- `sender_response_pattern` — if you typically respond to this person quickly, they're probably important
- Content analysis — direct questions, blocking language ("waiting on you," "can't proceed"), time-sensitive phrasing ("before EOD," "meeting in 30 min")
- `user_participated_in_thread` — active conversations you're part of are more relevant
- `mentions_user_directly` — explicit @mentions within a thread signal higher urgency

**Channel triage path** (for messages in monitored channels):

The primary question: "Does this match a condition I've told Alfred to watch for?"

Signals weighted heavily:
- `channel_keyword_rules` — user-configured keyword patterns (e.g., "outage," "down," "P0," "CI broken")
- `channel_priority` — user-assigned priority level for this channel
- Semantic analysis — the LLM evaluates whether the message indicates a situation the user would want to know about, even if no exact keyword matches (e.g., "the deploy pipeline has been stuck for 2 hours" matches the intent of "CI broken" without using those exact words)
- Severity detection — the LLM assesses the severity of the reported issue (informational vs. degraded vs. critical)

### 5.3 Classification prompt structure

The system prompt should instruct the LLM to:
1. Consider all provided metadata signals
2. Apply the appropriate classification path (DM vs. channel)
3. Output the structured JSON response
4. Default to `digest` when uncertain — false negatives (missing something urgent) are worse than false positives (over-notifying), but the system should err toward fewer interruptions in ambiguous cases
5. Treat VIP senders with higher baseline urgency
6. For channel messages, respect user-configured keyword rules as strong signals

The prompt must not include instructions that would cause the LLM to reproduce the message text in its output beyond the one-line `abstract`.

### 5.4 Classification thresholds

Users can configure their own sensitivity level, which adjusts the classifier's behavior:

| Sensitivity | Behavior |
|---|---|
| Low | Only VIP + explicit keyword matches trigger urgent. Most messages go to digest. |
| Medium (default) | Balanced — LLM semantic analysis active, moderate urgency threshold. |
| High | Aggressive alerting — lower threshold for urgent, more messages surfaced at break. |

This is implemented by including the sensitivity level in the classification prompt, not by post-processing the LLM output.

---

## 6. Notification and digest delivery

### 6.1 Urgent notifications

When a message is classified as `urgent`:

1. Store the `TriageClassification` record in PostgreSQL
2. Send a DM to the Alfred user via the Alfred Slack bot containing:
   - The sender name and channel
   - The one-line abstract
   - A link to the original Slack message
3. Fire an SSE event to the Alfred web UI that triggers the existing notification banner and alert sound (reusing the same notification infrastructure as focus mode bypass alerts)

**SSE event payload:**
```json
{
  "event_type": "triage.urgent",
  "data": {
    "sender_name": "Sarah Chen",
    "channel_name": "#support",
    "abstract": "Reports production API returning 500 errors",
    "slack_permalink": "https://workspace.slack.com/archives/C123/p1234567890",
    "classification_reason": "Keyword match: production error. Channel priority: high.",
    "timestamp": "2026-03-21T14:32:00Z"
  }
}
```

### 6.2 Review-at-break notifications

When a message is classified as `review_at_break`:

1. Store the `TriageClassification` record in PostgreSQL, tagged with the current focus session
2. When the Pomodoro timer transitions from work → break, collect all `review_at_break` records for this session that haven't been surfaced yet
3. Send a DM to the Alfred user via the Alfred Slack bot containing the batch of review items:
   - Each item includes sender name, one-line abstract, and Slack permalink
   - Grouped by channel when multiple items are from the same channel
4. Fire a lightweight SSE event to the Alfred web UI that displays a header notification prompting the user to check their Slack DMs. This header notification auto-clears when the break period ends.
5. Mark these records as `surfaced_at_break = true`

**SSE event payload (header notification only — content is in Slack DM):**
```json
{
  "event_type": "triage.break_check_slack",
  "data": {
    "item_count": 3,
    "message": "You have 3 messages to review — check your Alfred DMs in Slack"
  }
}
```

**Break end behavior:** When the Pomodoro break period ends (transitioning back to work), fire an SSE event to clear the header notification in the Alfred UI:
```json
{
  "event_type": "triage.break_notification_clear"
}
```

### 6.3 Post-focus digest

The digest is always delivered via Alfred Slack bot DM. This is not optional or configurable — the digest is always sent to Slack.

**Trigger conditions:**
- Focus session ends naturally (timer expires)
- Focus session ends early (user manually ends focus)
- Pomodoro cycle completes all sessions

In all cases, the digest is generated and delivered immediately upon focus session termination, regardless of how the session ended.

**Digest generation flow:**
1. On focus session end (any trigger), query all `TriageClassification` records for this focus session
2. Group by channel and thread
3. Run an LLM summarization pass that produces a structured digest:
   - Grouped by channel/conversation
   - Each item includes the stored `abstract` and `slack_permalink` (clickable link to the original Slack message/thread)
   - Action items and direct questions highlighted
   - Items that were already surfaced (urgent notifications, break reviews, bypass escalations) are marked as "already seen"
4. Send the digest as a DM from the Alfred bot to the user in Slack

**Digest format (Slack DM):**
```
📋 *Focus session summary* (2:00 PM — 3:45 PM)

*#support* (3 messages)
• Sarah Chen: Production API returning 500 errors ⚡ _Already notified_
  <https://workspace.slack.com/archives/C123/p1234567890|View in Slack>
• Jake Liu: Error rate back to normal after rollback
  <https://workspace.slack.com/archives/C123/p1234567891|View in Slack>
• Sarah Chen: Post-mortem scheduled for tomorrow 10 AM
  <https://workspace.slack.com/archives/C123/p1234567892|View in Slack>

*DMs* (2 messages)
• Mike Torres: Asked about Q3 roadmap timeline 📋 _Reviewed at break_
  <https://workspace.slack.com/archives/D456/p1234567893|View in Slack>
• Lisa Park: Shared design mockups for review — no rush
  <https://workspace.slack.com/archives/D789/p1234567894|View in Slack>
```

### 6.4 Slack permalink generation

Slack deep links are generated at triage time from available metadata and stored in the classification record:

```
Format: https://{workspace_domain}.slack.com/archives/{channel_id}/p{message_ts_without_dot}

Example:
  workspace_domain: mycompany (auto-detected during Slack account linking)
  channel_id: C0123456789
  message_ts: 1711036320.123456
  permalink: https://mycompany.slack.com/archives/C0123456789/p1711036320123456

For threaded messages, append ?thread_ts={thread_ts_no_dot}:
  https://mycompany.slack.com/archives/C0123456789/p1711036320123456?thread_ts=1711036000000000
```

The Slack workspace domain is auto-detected during Slack account linking by calling the `team.info` Slack API method and stored in `triage_user_settings.slack_workspace_domain`.

---

## 7. Channel monitoring configuration

### 7.1 Data model

**`monitored_channels` table:**

| Column | Type | Description |
|---|---|---|
| `id` | UUID | Primary key |
| `user_id` | UUID | Foreign key to users (tenant scoping) |
| `slack_channel_id` | VARCHAR | Slack channel ID |
| `channel_name` | VARCHAR | Display name (synced from Slack) |
| `channel_type` | ENUM | `public` / `private` |
| `priority` | ENUM | `low` / `medium` / `high` / `critical` |
| `is_active` | BOOLEAN | Whether monitoring is currently enabled |
| `created_at` | TIMESTAMP | |
| `updated_at` | TIMESTAMP | |

**`channel_keyword_rules` table:**

| Column | Type | Description |
|---|---|---|
| `id` | UUID | Primary key |
| `monitored_channel_id` | UUID | Foreign key to monitored_channels |
| `user_id` | UUID | Foreign key to users (redundant for query efficiency + tenant scoping) |
| `keyword_pattern` | VARCHAR | Keyword or phrase to match (case-insensitive) |
| `match_type` | ENUM | `exact` / `contains` / `semantic` |
| `urgency_override` | ENUM | `urgent` / `review_at_break` / `null` (let classifier decide) |
| `created_at` | TIMESTAMP | |

**`channel_source_exclusions` table:**

| Column | Type | Description |
|---|---|---|
| `id` | UUID | Primary key |
| `monitored_channel_id` | UUID | Foreign key to monitored_channels |
| `user_id` | UUID | Foreign key to users |
| `slack_entity_id` | VARCHAR | Slack user ID or bot ID to exclude/include |
| `entity_type` | ENUM | `bot` / `user` |
| `action` | ENUM | `exclude` / `include` |
| `display_name` | VARCHAR | Human-readable name for the UI |
| `created_at` | TIMESTAMP | |

### 7.2 Default behaviors

**Bot message filtering:**
- Messages with `bot_id` present in the Slack event payload or with `subtype: "bot_message"` are skipped by default (global behavior)
- Users can override this per channel by adding an explicit `include` rule for a specific bot (e.g., "Include PagerDuty alerts in #support")

**Default keyword suggestions:**
When a user adds a monitored channel, suggest (but don't auto-enable) common patterns:

- `outage`, `down`, `incident` → urgency override: `urgent`
- `blocked`, `blocker`, `broken` → urgency override: `review_at_break`
- `deploy`, `rollback`, `hotfix` → urgency override: `review_at_break`
- `P0`, `P1`, `SEV1`, `SEV2` → urgency override: `urgent`

Users can add, edit, or remove patterns. The `semantic` match type uses the LLM to match intent rather than exact text (e.g., "the pipeline has been stuck for hours" matches the intent of "CI broken").

### 7.3 API endpoints

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/triage/channels` | List user's monitored channels |
| `POST` | `/api/triage/channels` | Add a monitored channel |
| `PATCH` | `/api/triage/channels/{id}` | Update channel config (priority, active status) |
| `DELETE` | `/api/triage/channels/{id}` | Remove a monitored channel |
| `GET` | `/api/triage/channels/{id}/rules` | List keyword rules for a channel |
| `POST` | `/api/triage/channels/{id}/rules` | Add a keyword rule |
| `PATCH` | `/api/triage/channels/{id}/rules/{rule_id}` | Update a keyword rule |
| `DELETE` | `/api/triage/channels/{id}/rules/{rule_id}` | Delete a keyword rule |
| `GET` | `/api/triage/channels/{id}/exclusions` | List source exclusions for a channel |
| `POST` | `/api/triage/channels/{id}/exclusions` | Add a source exclusion/inclusion |
| `DELETE` | `/api/triage/channels/{id}/exclusions/{exclusion_id}` | Remove a source exclusion/inclusion |
| `GET` | `/api/slack/channels/available` | List Slack channels available for monitoring (channels the linked Slack user is a member of) |

### 7.4 UI requirements

The channel monitoring configuration lives in the Alfred web UI Settings page, alongside existing integrations:

- Channel picker: searchable dropdown of available Slack channels (fetched from Slack API via the user's linked account)
- Per-channel priority selector
- Per-channel keyword rule editor (add/remove patterns, set match type and urgency override)
- Per-channel source exclusion manager (list bots/users in the channel, toggle exclude/include)
- Toggle to enable/disable monitoring per channel without removing the configuration
- Note: since Alfred uses user event subscriptions, the bot does not need to be added to channels. The available channels are those the user's linked Slack account is a member of.

---

## 8. Slack response analytics

### 8.1 Purpose

Provide users with data about their own Slack response patterns to (a) power the sender behavioral model used by the classifier and (b) help users understand their habits and build confidence in the triage system.

### 8.2 Behavioral model computation

The sender behavioral model is computed from Slack conversation history and stored per Alfred user per Slack sender:

**`sender_behavior_model` table:**

| Column | Type | Description |
|---|---|---|
| `id` | UUID | Primary key |
| `user_id` | UUID | Foreign key to users |
| `sender_slack_id` | VARCHAR | The Slack user this model describes |
| `avg_response_time_seconds` | INTEGER | Average time to first reply |
| `response_pattern` | ENUM | `fast_responder` / `normal` / `slow_responder` |
| `interaction_frequency` | ENUM | `high` / `medium` / `low` |
| `total_interactions` | INTEGER | Number of conversations analyzed |
| `last_computed_at` | TIMESTAMP | When this model was last updated |

**Computation:**
- Bootstrapped by calling `conversations.history` for the user's DM channels (requires user token with `im:history`)
- Recomputed daily via a scheduled ARQ job
- `fast_responder`: avg response time < 5 minutes
- `normal`: avg response time 5–60 minutes
- `slow_responder`: avg response time > 60 minutes
- `interaction_frequency` based on message count in the last 30 days: high (>50), medium (10–50), low (<10)

### 8.3 Analytics dashboard (web UI)

Display on a dedicated page or as a section in the existing focus mode UI:

- **Response time distribution**: histogram of your response times across all senders
- **Top senders by response speed**: who you consistently reply to fastest
- **Triage accuracy**: after each focus session, the user can rate the digest ("was anything misclassified?") — track this over time
- **Check frequency**: if the user opens Slack during a focus session (detectable via focus mode end time vs. scheduled end time), log it as a "manual check" for trend tracking
- **Messages triaged per session**: volume and classification breakdown (urgent / break / digest)

### 8.4 API endpoints

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/triage/analytics/response-patterns` | Sender response time data |
| `GET` | `/api/triage/analytics/session-stats` | Per-session triage statistics |
| `POST` | `/api/triage/analytics/feedback` | User feedback on classification accuracy |
| `POST` | `/api/triage/analytics/recompute` | Trigger manual recomputation of behavioral models |

---

## 9. Debugging and test logging

### 9.1 Triage debug logger

A dedicated logger (`alfred.triage`) provides full pipeline observability without violating the zero-persistence constraint on message content.

**Log levels and what they capture:**

| Level | What is logged | Example |
|---|---|---|
| `DEBUG` | Full pipeline trace per message (no content) | `Triage job started: user_id=abc, channel=C123, sender=U456, message_ts=1711036320.123` |
| `DEBUG` | Enrichment metadata attached | `Enrichment: is_vip=false, response_pattern=fast, channel_priority=high, keyword_matches=["outage"]` |
| `DEBUG` | LLM classification input/output (abstract only, not raw message) | `Classification result: urgency=urgent, confidence=0.92, abstract="Reports production API errors"` |
| `INFO` | Classification summary per message | `Classified message in #support as urgent (confidence: 0.92) for user abc` |
| `INFO` | Digest generation events | `Generated focus session digest: 12 messages, 2 urgent, 3 break, 7 digest` |
| `WARNING` | LLM classification timeout or error | `Classification failed for message_ts=1711036320.123 — defaulting to review_at_break` |
| `ERROR` | Unhandled exceptions in the triage pipeline | Full stack trace (still no message content) |

### 9.2 What is never logged

- Raw Slack message text at any log level
- Message attachments or file metadata
- Full LLM prompt contents (which include message text)
- Any PII beyond Slack user IDs (which are opaque identifiers)

### 9.3 Structured log format

All triage log entries include structured fields for filtering and correlation:

```json
{
  "logger": "alfred.triage",
  "level": "INFO",
  "timestamp": "2026-03-21T14:32:01.234Z",
  "correlation_id": "triage-abc123-1711036320",
  "user_id": "abc-def-ghi",
  "channel_id": "C0123456789",
  "sender_slack_id": "U9876543210",
  "message_ts": "1711036320.123456",
  "pipeline_stage": "classification",
  "urgency": "urgent",
  "confidence": 0.92,
  "latency_ms": 1847,
  "message": "Classified message in #support as urgent"
}
```

The `correlation_id` is generated per triage job and threads through all log entries for that message, enabling end-to-end trace reconstruction.

### 9.4 Testing strategy

**Unit tests:**
- Triage classifier with mocked LLM responses — verify classification logic for each path (DM, channel, VIP, keyword match)
- Message collector enrichment with mocked Slack API and database responses
- Permalink generation from various `channel_id` and `message_ts` formats
- Zero-persistence verification: assert that no test writes message text to the database
- Multi-tenant isolation: assert that triage jobs for User A never access User B's configuration
- Source exclusion filtering: verify bot messages are skipped by default, include overrides work, user exclusions are per-channel
- Redis monitored channel set: verify set updates on add/remove, fallback to DB on cache miss

**Integration tests:**
- End-to-end triage pipeline with a real (test) LLM call
- ARQ job enqueue → process → classification record created
- Focus session end (natural and early termination) → digest generation → Slack DM sent
- Pomodoro break transition → review-at-break DM sent → header notification SSE fired → break end clears notification
- Bypass button interaction + triage running in parallel — verify no interference
- Multi-user fan-out: message in shared monitored channel → separate triage jobs for each user

**Load tests:**
- Simulate 50+ messages/minute for a single user — verify queue depth, latency, and no dropped classifications
- Simulate 10 concurrent users with overlapping monitored channels — verify tenant isolation under load

### 9.5 Debug mode

A per-user debug toggle (stored in user settings) that, when enabled:
- Increases the triage logger to `DEBUG` level for that user's jobs only
- Includes the `classification_reason` and all enrichment metadata in SSE events (so the web UI can display "why was this classified as urgent?")
- Adds a "Debug" panel to the web UI triage view showing the full enrichment payload and classification reasoning for each message (still excluding raw message text)

This is intended for development and troubleshooting, not for production use by all users.

---

## 10. Data model summary

### 10.1 New tables

```
monitored_channels
├── id (UUID, PK)
├── user_id (UUID, FK → users)
├── slack_channel_id (VARCHAR)
├── channel_name (VARCHAR)
├── channel_type (ENUM: public, private)
├── priority (ENUM: low, medium, high, critical)
├── is_active (BOOLEAN, default true)
├── is_hidden (BOOLEAN, default false)
├── triage_instructions (TEXT, NULLABLE)  -- Per-channel custom instructions
├── created_at (TIMESTAMP)
└── updated_at (TIMESTAMP)

channel_source_exclusions
├── id (UUID, PK)
├── monitored_channel_id (UUID, FK → monitored_channels)
├── user_id (UUID, FK → users)
├── slack_entity_id (VARCHAR)
├── entity_type (ENUM: bot, user)
├── action (ENUM: exclude, include)
├── display_name (VARCHAR)
└── created_at (TIMESTAMP)

triage_classifications
├── id (UUID, PK)
├── user_id (UUID, FK → users)
├── focus_session_id (UUID, FK → focus_mode_state, NULLABLE)
├── sender_slack_id (VARCHAR)
├── sender_name (VARCHAR, NULLABLE)
├── channel_id (VARCHAR)
├── channel_name (VARCHAR, NULLABLE)
├── message_ts (VARCHAR)
├── thread_ts (VARCHAR, NULLABLE)
├── slack_permalink (TEXT, NULLABLE)
├── focus_started_at (TIMESTAMP, NULLABLE)
├── priority_level (ENUM: p0, p1, p2, p3, review, digest_summary)
├── confidence (FLOAT)
├── classification_reason (TEXT, NULLABLE)
├── abstract (TEXT, NULLABLE)
├── classification_path (ENUM: dm, channel)
├── escalated_by_sender (BOOLEAN, default false)
├── surfaced_at_break (BOOLEAN, default false)
├── keyword_matches (JSON, NULLABLE)
├── reviewed_at (TIMESTAMP, NULLABLE)
├── digest_summary_id (UUID, FK → triage_classifications, NULLABLE)
├── child_count (INTEGER, NULLABLE)
├── last_alerted_at (TIMESTAMP, NULLABLE)
├── alert_count (INTEGER, default 0)
├── queued_for_digest (BOOLEAN, default true)
├── digest_type (VARCHAR: focus, scheduled, NULLABLE)
└── created_at (TIMESTAMP)

sender_behavior_model
├── id (UUID, PK)
├── user_id (UUID, FK → users)
├── sender_slack_id (VARCHAR)
├── avg_response_time_seconds (FLOAT, NULLABLE)
├── response_pattern (ENUM: immediate, quick, normal, slow)
├── interaction_frequency (ENUM: high, medium, low, rare)
├── total_interactions (INTEGER)
├── last_computed_at (TIMESTAMP, NULLABLE)
└── UNIQUE(user_id, sender_slack_id)

triage_user_settings
├── id (UUID, PK)
├── user_id (UUID, FK → users, UNIQUE)
├── is_always_on (BOOLEAN, default false)
├── sensitivity (ENUM: low, medium, high, default medium)
├── debug_mode (BOOLEAN, default false)
├── slack_workspace_domain (VARCHAR, NULLABLE)
├── classification_retention_days (INTEGER, default 30)
├── custom_classification_rules (TEXT, NULLABLE)
├── p0_definition (TEXT, NULLABLE)
├── p1_definition (TEXT, NULLABLE)
├── p2_definition (TEXT, NULLABLE)
├── p3_definition (TEXT, NULLABLE)
├── digest_instructions (TEXT, NULLABLE)
│   -- P1 digest cadence
├── p1_digest_interval_minutes (INTEGER, NULLABLE)
├── p1_digest_active_hours_start (VARCHAR, NULLABLE)
├── p1_digest_active_hours_end (VARCHAR, NULLABLE)
├── p1_digest_times (ARRAY<VARCHAR>, NULLABLE)
├── p1_digest_outside_hours_behavior (VARCHAR, NULLABLE)
│   -- P2 digest cadence
├── p2_digest_interval_minutes (INTEGER, NULLABLE)
├── p2_digest_active_hours_start (VARCHAR, NULLABLE)
├── p2_digest_active_hours_end (VARCHAR, NULLABLE)
├── p2_digest_times (ARRAY<VARCHAR>, NULLABLE)
├── p2_digest_outside_hours_behavior (VARCHAR, NULLABLE)
│   -- P3 digest cadence
├── p3_digest_time (VARCHAR, NULLABLE)
│   -- Alert configuration
├── alert_dedup_window_minutes (INTEGER, default 30)
├── p0_alerts_enabled (BOOLEAN, default true)
├── p1_alerts_enabled (BOOLEAN, default true)
├── p2_alerts_enabled (BOOLEAN, default true)
├── p3_alerts_enabled (BOOLEAN, default true)
├── created_at (TIMESTAMP)
└── updated_at (TIMESTAMP)

slack_channel_cache
├── id (UUID, PK)
├── slack_channel_id (VARCHAR, UNIQUE)
├── name (VARCHAR)
├── is_private (BOOLEAN)
├── num_members (INTEGER)
├── created_at (TIMESTAMP)
└── updated_at (TIMESTAMP)

triage_feedback
├── id (UUID, PK)
├── user_id (UUID, FK → users)
├── classification_id (UUID, FK → triage_classifications)
├── was_correct (BOOLEAN)
├── correct_priority (ENUM: p0, p1, p2, p3, review, NULLABLE)
├── feedback_text (TEXT, NULLABLE)
└── created_at (TIMESTAMP)
```

### 10.2 Indexes

```sql
CREATE INDEX idx_triage_classifications_user_session
  ON triage_classifications(user_id, focus_session_id);
CREATE INDEX idx_triage_classifications_user_created
  ON triage_classifications(user_id, created_at DESC);
CREATE INDEX idx_triage_classifications_digest_summary
  ON triage_classifications(digest_summary_id);
CREATE INDEX idx_monitored_channels_user
  ON monitored_channels(user_id);
CREATE INDEX idx_monitored_channels_slack
  ON monitored_channels(slack_channel_id);
CREATE INDEX idx_channel_source_exclusions_channel
  ON channel_source_exclusions(monitored_channel_id);
CREATE INDEX idx_sender_behavior_user
  ON sender_behavior_model(user_id, sender_slack_id);
CREATE INDEX idx_slack_channel_cache_name
  ON slack_channel_cache(name);
```

### 10.3 Data retention

Triage classification records are retained for a user-configurable number of days (default: 30, stored in `triage_user_settings.classification_retention_days`). A scheduled ARQ job runs daily to delete expired records:

```sql
DELETE FROM triage_classifications
WHERE created_at < NOW() - INTERVAL '1 day' * (
  SELECT classification_retention_days
  FROM triage_user_settings
  WHERE triage_user_settings.user_id = triage_classifications.user_id
);
```

The retention setting is configurable by the user in the Alfred web UI under Settings > Triage.

---

## 11. API endpoints summary

### 11.1 Triage configuration

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/triage/settings` | Get user's triage settings |
| `PATCH` | `/api/triage/settings` | Update triage settings (sensitivity, always-on, retention days, debug mode) |

### 11.2 Channel monitoring

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/triage/channels` | List monitored channels |
| `POST` | `/api/triage/channels` | Add monitored channel |
| `PATCH` | `/api/triage/channels/{id}` | Update channel config (priority, instructions, active) |
| `DELETE` | `/api/triage/channels/{id}` | Remove monitored channel |
| `GET` | `/api/triage/channels/{id}/exclusions` | List source exclusions |
| `POST` | `/api/triage/channels/{id}/exclusions` | Add source exclusion/inclusion |
| `DELETE` | `/api/triage/channels/{id}/exclusions/{exclusion_id}` | Remove source exclusion/inclusion |
| `GET` | `/api/triage/slack-channels` | List Slack channels the user is a member of |
| `GET` | `/api/triage/channels/{id}/exclusions` | List source exclusions |
| `POST` | `/api/triage/channels/{id}/exclusions` | Add source exclusion/inclusion |
| `DELETE` | `/api/triage/channels/{id}/exclusions/{exclusion_id}` | Remove source exclusion/inclusion |
| `GET` | `/api/slack/channels/available` | List Slack channels the user is a member of |

### 11.3 Triage results

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/triage/classifications` | List recent classifications (paginated, filterable by priority) |
| `PATCH` | `/api/triage/classifications/reviewed` | Bulk mark reviewed/unreviewed |
| `GET` | `/api/triage/classifications/{id}/digest-children` | Get digest summary children |
| `GET` | `/api/triage/digest/{session_id}` | Get digest for a specific focus session |
| `GET` | `/api/triage/digest/latest` | Get the most recent classifications as digest |

### 11.4 Analytics and calibration

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/triage/analytics/session-stats` | Per-session triage statistics by priority |
| `POST` | `/api/triage/analytics/feedback` | Submit classification accuracy feedback |
| `POST` | `/api/triage/wizard/definitions` | AI-generated custom priority definitions |
| `POST` | `/api/triage/calibration/sample` | Sample Slack messages for calibration |
| `POST` | `/api/triage/calibration/generate` | Generate definitions from user ratings |

### 11.5 SSE event types (via existing `/api/notifications`)

| Event type | Trigger | Payload |
|---|---|---|
| `triage.urgent` | Message classified as P0 | sender, channel, abstract, permalink, reason |
| `triage.break_check_slack` | Focus break with digest items or scheduled digest ready | item count, prompt to check Slack DMs |
| `triage.break_notification_clear` | Digest reviewed | (empty — clears header notification) |
| `triage.debug` | Debug mode enabled | Full enrichment payload and classification reasoning |

---

## 12. Implementation phases

### Phase 1: Foundation ✅ Complete
- Database migrations for all new tables
- `TriageUserSettings` model and API
- `MonitoredChannel` and `ChannelSourceExclusion` models and APIs
- Dedicated ARQ triage queue configuration
- Redis monitored channel set with cache invalidation
- `alfred.triage` structured logger setup
- Auto-detect Slack workspace domain during account linking (`team.info` API call)
- Basic Settings UI for channel monitoring configuration and source exclusions
- Slack channel cache for efficient channel list retrieval

### Phase 2: Triage pipeline ✅ Complete
- Message collector with in-memory enrichment
- Thread context summarization for channel messages
- DM conversation context summarization for DMs
- Slack event handler modifications (parallel triage job enqueue, pre-filtering)
- Bot/source exclusion filtering (global default + per-channel overrides)
- DM triage classifier (LLM integration)
- Channel triage classifier with per-channel instructions
- P0 (urgent) notification delivery: Slack DM via Alfred bot + SSE banner/sound in Alfred UI
- Alert deduplication within configurable window
- Integration with existing focus mode bypass flow (escalated_by_sender flag)
- Zero-persistence verification tests

### Phase 3: Digest and delivery ✅ Complete
- Scheduled digest delivery with configurable cadence per priority level
- P1/P2 digests at configurable intervals/times
- P3 daily summary
- Post-focus digest generation (LLM summarization) — triggered on both natural and early focus session end
- Digest delivery via Alfred Slack bot DM (always, not optional)
- Slack permalink generation and validation
- Data retention job (daily cleanup based on user-configurable retention days)
- Digest consolidation with parent-child relationships

### Phase 4: Analytics and polish ✅ Complete
- Sender behavioral model computation (bootstrap + daily recompute)
- Analytics dashboard UI
- Classification feedback mechanism
- Debug mode implementation
- Priority calibration system with sampled messages
- Triage Wizard for AI-generated priority definitions
- Per-priority alert toggles (p0_alerts_enabled, etc.)
- Custom priority definitions (p0_definition through p3_definition)
- End-to-end integration test suite

---

## 13. Resolved decisions

| # | Question | Decision |
|---|---|---|
| 1 | Slack workspace domain for permalinks | Auto-detect during Slack account linking via `team.info` API call. Stored in `triage_user_settings.slack_workspace_domain`. |
| 2 | Always-on urgent notification delivery | Delivered via Alfred Slack bot DM + SSE event that triggers the existing notification banner and alert sound in the Alfred web UI. |
| 3 | Channel message volume limits | No backpressure threshold for initial launch. Monitor performance and add if needed in a future iteration. |
| 4 | Digest retention | Default 30 days, configurable by the user in the UI. Stored in `triage_user_settings.classification_retention_days`. Daily cleanup job. |
| 5 | Bot channel membership for monitoring | Not required. Alfred uses Slack user event subscriptions — the bot receives events from channels the linked Slack user is a member of. If monitoring requires the bot to be in a channel (edge case), notify the user via Alfred UI and Slack bot DM with instructions. Do not auto-join. |
| 6 | Priority levels | Four levels: P0 (urgent), P1 (high), P2 (medium), P3 (low), plus "review" for uncertain cases. User-customizable definitions via Triage Wizard or manual settings. |
| 7 | Keyword rules | Replaced by per-channel `triage_instructions` text field. More flexible than rigid keyword matching. |
| 8 | Alert deduplication | Implemented via `alert_dedup_window_minutes` (default 30 min). Prevents notification spam from rapid messages in same channel/thread. |
| 9 | Digest cadence | Configurable per priority level. P1/P2 support intervals, active hours, and specific times. P3 is daily summary only. |
| 10 | Priority calibration | Users can sample real Slack messages and rate them P0-P3. The Triage Wizard uses these ratings to generate custom priority definitions. |
