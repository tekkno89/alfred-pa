# Digest Grouping & Quality Improvements

## Overview

Improve P1-P3 digest to: (1) group by thread instead of per-message, (2) filter trivial messages, (3) produce high-quality summaries with named participants, subjects, and outcomes.

**Problem**: 8 messages from one Slack thread produced 8 separate digest rows, each a low-quality single-clause summary like "User stated X" or "Message contains only an emoji."

## Scope

### In Scope
- Deterministic thread grouping with full thread context fetching
- Substance filter for standalone messages (emoji-only, "thanks", "ok", etc.)
- Incremental thread summarization (CONTEXT vs NEW message sets)
- Summary quality improvements (named participants, 1-2 sentences, subject + outcome)
- LLM clustering for unthreaded messages (Phase 2)
- Database tracking for processed/filtered messages via `processed_reason` column

### Out of Scope
- Cross-channel correlation or merging threads across channels
- Refactoring digest pipeline into LangGraph agent or tool-access
- Changing P0 urgent-message path
- New user-facing settings or UI (backend config/constants only)
- Persisting clusters across digest runs (v1 limitation)

---

## Phase 1 — Thread Grouping + Substance Filter + Summary Quality

### 1.1 Database Migration: `processed_reason` Column

**Why not reuse existing fields**: `queued_for_digest=False` + `last_alerted_at=now()` conflates three distinct outcomes:
- (a) summarized and delivered
- (b) filtered as non-substantive
- (c) absorbed into a thread or cluster summary

**Migration**: Add nullable `processed_reason` column to `triage_classifications`:

```python
# backend/app/db/models/triage.py
processed_reason: Mapped[str | None] = mapped_column(String(30), nullable=True)
```

**Values**:
- `summarized` — message was summarized and delivered
- `filtered_nonsubstantive` — dropped by substance filter (standalone)
- `absorbed_in_thread` — part of thread summary (not the focus message)
- `absorbed_in_cluster` — part of Phase 2 cluster summary
- `skipped_thin_update` — NEW set had zero substantive messages

**Command**:
```bash
docker-compose -f docker-compose.dev.yml exec backend alembic revision --autogenerate -m "add processed_reason to triage_classifications"
docker-compose -f docker-compose.dev.yml exec backend alembic upgrade head
```

### 1.2 Substance Filter

Create `backend/app/services/substance_filter.py`:

**Module-level constant** (tunable):
```python
ACKNOWLEDGMENT_PATTERNS = [
    "ok", "okay", "k",
    "thanks", "thx", "ty", "np",
    "lgtm", "sgtm", "shipit",
    "got it", "sounds good", "will do", "done",
    "yep", "yup", "nope",
    "+1", "-1",
]

# Regex pattern for emoji-only detection
EMOJI_ONLY_PATTERN = re.compile(r'^[\s\p{Emoji}\p{Emoji_Presentation}\p{Emoji_Modifier}\p{Emoji_Modifier_Base}\p{Emoji_Component}:+\-\w]+$', re.UNICODE)
```

**Logic** (`is_substantive(msg: TriageClassification) -> bool`):
- Content is only emoji(s) or reaction-shorthand (`:+1:`, `:thumbsup:`, `👍`, `🎉`, etc.) → non-substantive
- Content matches acknowledgment pattern (case-insensitive, ignoring trailing punctuation/emoji) → non-substantive
- Content is under 10 characters with no alphanumeric substance beyond patterns → non-substantive
- Slack `subtype` is system notification (`channel_join`, `channel_leave`, `bot_add`, etc.) → non-substantive

**Application rules**:
- Single-message groups (no thread, no replies) → drop entirely if non-substantive, mark `processed_reason='filtered_nonsubstantive'`
- Multi-message thread groups → DO NOT filter inside; summarizer absorbs them
- Phase 2 clusters where EVERY message is non-substantive → drop cluster, mark `processed_reason='filtered_nonsubstantive'`

### 1.3 Thread Grouping with Full Context

Modify `backend/app/services/digest_grouper.py`:

**Current state**: Groups by `thread_ts` but only uses stored messages, not full thread.

**Changes**:
1. For groups with `thread_ts` OR groups with >1 pending message:
   - Fetch full thread via Slack `conversations.replies` using **user OAuth token** (via `SlackUserService.get_raw_token(user_id)`)
   - Cap at 200 replies, **keep most recent 200** (drop oldest)
   - Log truncation with thread_ts and dropped count
   - This becomes the CONTEXT set

2. The pending messages in our store for that thread are the NEW set

3. Pass both to summarizer with clear labels

**Why user OAuth token**: Bot may not be member of all monitored channels. Users ARE members. See CLAUDE.md "Slack Token Usage Guidelines".

**Group priority**: Max priority of member messages (existing behavior, preserve).

**Transaction safety**: Mark all messages in processed group with same `processed_reason` in single transaction.

### 1.4 Batch User Name Resolution

**Location**: Add to `backend/app/services/triage_enrichment.py` (co-located with existing single-user resolver).

**Why here**: Must share cache key format, fallback chain, and TTL with existing resolver to avoid drift.

**New function**:
```python
async def resolve_user_names_batch(
    slack_service: "SlackService",
    redis_client: "Redis",
    user_ids: set[str],
) -> dict[str, str]:
    """
    Resolve display names for multiple Slack user IDs.
    
    Uses same cache key format, fallback chain, and TTL as single-user resolver:
    - Cache key: slack:user_name:{user_id}
    - TTL: 24 hours
    - Fallback: real_name → profile.display_name → name → user_id
    """
```

**Refactor**: Update existing single-user resolver to call through batch internally (single becomes one-element batch).

**Usage in digest flow**:
1. Collect all unique user IDs from CONTEXT + NEW messages
2. Single pass through Redis cache
3. For cache misses: batched resolution via Slack API with cache-write
4. Never N+1 the API during summarization

### 1.5 Incremental Thread Summarization

Modify `backend/app/services/triage_delivery.py` `create_conversation_summary()`:

**First-run detection**:
```python
if set(context_message_ids) == set(new_message_ids):
    # First run - all messages are new, use plain summarization
    mode = "full"
else:
    # Incremental - distinguish CONTEXT vs NEW
    mode = "thread_incremental"
```

**Prompt structure for `thread_incremental` mode**:
```
CONTEXT (earlier messages in thread, already summarized):
<full thread messages up to but not including NEW>

NEW (messages added during this interval):
<only the pending messages>

Task: Summarize only the NEW messages. Use earlier messages purely as context to understand what's being discussed. Do not restate what was said before this interval.
```

**Prompt structure for `full` mode**:
```
Summarize this conversation:
<all messages>

Create a brief summary (1-2 sentences) that names participants and describes the subject and outcome.
```

**Zero-substantive-NEW check** (after thread grouping, NOT during substance filtering):
- Check: Does NEW set have any substantive messages?
- No: Mark all NEW messages as `processed_reason='skipped_thin_update'`, skip summarization
- Yes: Proceed with summarization

### 1.6 Two-Mode Summarizer

| Mode | When Used | Prompt Structure |
|------|-----------|------------------|
| `thread_incremental` | Phase 1 threads after first run | CONTEXT + NEW distinction |
| `full` | First-run threads, Phase 2 clusters, Phase 2 singletons | Summarize everything passed in |

Both modes share:
- Few-shot BAD/GOOD examples
- Named participants requirement
- 1-2 sentences, subject + outcome

### 1.7 Summary Quality

Update summarization prompt in `create_conversation_summary()`:

**Requirements**:
- At least 1-2 full sentences, never single clause/fragment
- Name participants by display name ("Mike and Sara discussed...")
- Never use "user" or "a user" - always use actual names
- State the subject — what was discussed, decided, or asked
- Include outcome or open question if there is one

**Few-shot examples in system prompt**:
```
BAD: "User stated the build is broken."
BAD: "A discussion occurred about deployment."
BAD: "Message contains only an emoji."
BAD: "User announces their return to the channel."

GOOD: "Caitlin flagged that the main branch build was failing. Max identified a stale Docker cache as the cause and Caitlin triggered a rebuild, which resolved the issue."
GOOD: "Sara asked whether to roll back the 3.2.1 release after a customer-reported regression. Mike agreed and took the rollback; root cause investigation is still open."
GOOD: "Raj shared the Q3 planning doc and asked the platform team for feedback on the migration timeline by Friday."
```

### 1.8 Tests (TDD — Write First)

**Unit tests** (`backend/tests/services/test_substance_filter.py`):
- [ ] Emoji-only message is non-substantive
- [ ] Acknowledgment patterns are non-substantive
- [ ] System notification subtypes are non-substantive
- [ ] Short alphanumeric message is substantive
- [ ] Message with real content + trailing "thanks" is substantive

**Unit tests** (`backend/tests/services/test_digest_grouper.py` - add):
- [x] 8 messages sharing `thread_ts` produce 1 group with CONTEXT/NEW distinction
- [x] 3 unthreaded substantive messages in different channels produce 3 independent summaries
- [x] Group with P2 + P3 message classified P2 in output
- [x] 6 pending: 2 substantive thread-parents + 4 standalone emoji/thanks → 2 summaries, 4 marked `processed_reason='filtered_nonsubstantive'`
- [x] Thread with all non-substantive NEW messages → 0 summaries, marked `processed_reason='skipped_thin_update'`
- [x] First-run thread (all messages NEW, none previously processed) uses `full` mode
- [x] Thread truncation keeps most recent 200 messages

**Unit test** (`backend/tests/services/test_triage_delivery.py` - add):
- [x] Summary fixture (Mike and Sara discussing rollback): contains both names, ≥2 sentences, no "user" literal
- [x] Two-mode summarizer: `thread_incremental` mode includes CONTEXT/NEW distinction
- [x] Two-mode summarizer: `full` mode summarizes all messages

**Unit test** (`backend/tests/services/test_triage_enrichment.py` - add):
- [x] `resolve_user_names_batch` returns names for all IDs
- [x] `resolve_user_names_batch` uses cache and writes to cache on miss
- [x] Single-user resolver calls through batch internally

**Integration tests** (`backend/tests/integration/test_digest_flow.py` - add):
- [ ] Mock `conversations.replies` called for threaded groups, skipped for single-message
- [ ] Partial LLM failure on one group doesn't mark other groups' messages
- [ ] Assert specific `processed_reason` values for different outcomes

### 1.9 Checklist

- [x] Add `processed_reason` column to `TriageClassification` model
- [x] Create migration via `alembic revision --autogenerate`
- [x] Run migration against dev DB
- [x] Add `mark_processed()` helper to `TriageClassificationRepository`
- [x] Create `backend/app/services/substance_filter.py` with `ACKNOWLEDGMENT_PATTERNS` constant and `is_substantive()` function
- [x] Add unit tests for substance filter
- [x] Add `resolve_user_names_batch()` to `triage_enrichment.py`
- [x] Refactor single-user resolver to call through batch
- [x] Modify `DigestGrouper` to fetch full thread context via `conversations.replies`
- [x] Pass user OAuth token via `SlackUserService.get_raw_token(user_id)`
- [x] Implement thread truncation (keep most recent 200)
- [x] Distinguish CONTEXT vs NEW message sets
- [x] Implement first-run detection
- [x] Implement two-mode summarizer (`thread_incremental` / `full`)
- [x] Update `create_conversation_summary()` with new prompt structure
- [x] Add few-shot examples to summarization prompt
- [x] Enforce quality requirements (named participants, 1-2 sentences, subject + outcome)
- [x] Handle zero-substantive-messages case in thread summarization
- [x] Add tests for thread grouping with CONTEXT/NEW
- [x] Add tests for first-run detection
- [x] Add tests for two-mode summarizer
- [x] Add tests for summary quality
- [x] Add tests for batch name resolution
- [x] Wire substance filter into `send_digest()` worker task
- [x] Mark messages with appropriate `processed_reason` values
- [x] Run `pytest` - all tests pass
- [x] Run `ruff check .` - clean
- [ ] Manual test: channel with active multi-message thread produces 1 summary
- [ ] Manual test: channel with standalone emoji/thanks produces 0 summaries
- [x] Update `triage-flow.md` diagram

---

## Phase 2 — LLM Clustering for Unthreaded Messages

**Prerequisite**: Phase 1 shipped and verified.

### 2.1 Partitioning Strategy

The digest cadence is **per-user configurable**, so the pending pool varies widely. Partition by message count, not time:

**Module-level constants**:
```python
# Tuned based on observation; adjust if Phase 2 clusters look wrong.
MAX_CLUSTERING_BATCH_SIZE = 40
CONVERSATION_GAP_THRESHOLD_MINUTES = 10
```

**Rules**:
- If a channel has ≤ 40 messages in pending pool → single clustering call
- If a channel has > 40 messages → subdivide into consecutive windows of ~40 messages each
  - **Gap selection**: Find all gaps >= 10 minutes between consecutive messages
  - If multiple gaps exist, pick one closest to midpoint (most balanced partition)
  - Otherwise, split at midpoint by count
- Never send > 40 messages in a single clustering call

**Gap selection algorithm**:
```python
def find_split_point(messages: list, gap_threshold_minutes: int = 10) -> int:
    """
    Find best split point for a batch of messages.
    
    1. Find all gaps >= gap_threshold_minutes between consecutive messages
    2. If gaps exist, pick one closest to midpoint (len(messages) // 2)
    3. Otherwise, split at midpoint by count
    """
    midpoint = len(messages) // 2
    
    gaps = []
    for i in range(1, len(messages)):
        time_diff = parse_ts(messages[i].ts) - parse_ts(messages[i-1].ts)
        if time_diff >= timedelta(minutes=gap_threshold_minutes):
            gaps.append((i, abs(i - midpoint)))
    
    if gaps:
        best_gap = min(gaps, key=lambda x: x[1])
        return best_gap[0]
    
    return midpoint
```

### 2.2 Clustering Call

**Payload format** (JSON array):
```json
[
  {"id": "msg_id_1", "user": "Mike", "ts": "1234567890.001", "preview": "First 200 chars..."},
  {"id": "msg_id_2", "user": "Sara", "ts": "1234567890.002", "preview": "First 200 chars..."}
]
```

- `user` is resolved display name, not raw Slack ID
- `preview` is message text truncated to 200 characters

**Output format** (JSON schema, temperature 0):
```json
{
  "clusters": [
    {"cluster_id": "c1", "message_ids": ["msg_id_1", "msg_id_2"]},
    {"cluster_id": "c2", "message_ids": ["msg_id_3"]}
  ]
}
```

**Prompt requirements**:
- Explicitly allow singleton clusters (AFKs, standalone announcements, off-topic one-liners)
- Give examples of what belongs in singleton vs multi-message clusters
- Without this, models over-merge

### 2.3 Post-Clustering

- Multi-message clusters → feed to `full` mode summarizer
- Singleton clusters → `full` mode summarizer (same quality rules)
- Clusters where every message is non-substantive → drop and mark `processed_reason='filtered_nonsubstantive'`

### 2.4 Graceful Degradation

- Malformed JSON from model → treat every message as singleton cluster
- Never lose messages due to clustering failure

### 2.5 Tests

- [x] Partition with 5-message coherent back-and-forth + 2 unrelated one-liners produces ≥2 clusters
- [x] Partition with 1 message skips clustering call entirely
- [x] Malformed JSON falls back to singleton clusters
- [x] Clustering called at most once per channel per run (not once per message)
- [x] 41 messages in channel split into 2 batches
- [x] Natural gap (10+ min) preferred as split point when available
- [x] Multiple gaps: pick one closest to midpoint

### 2.6 Checklist

- [x] Add `MAX_CLUSTERING_BATCH_SIZE = 40` and `CONVERSATION_GAP_THRESHOLD_MINUTES = 10` constants
- [x] Implement partitioning logic with gap selection algorithm
- [x] Build clustering prompt with singleton examples
- [x] Use structured output / JSON schema for model response
- [x] Implement graceful fallback on malformed JSON
- [x] Wire into digest flow AFTER Phase 1 thread grouping + substance filter
- [x] Use `full` mode summarizer for clusters
- [x] Add tests
- [ ] Manual test with >40 unthreaded messages in single channel

---

## Known Limitations / v1 Tradeoffs

### Conversations Spanning Digest-Run Boundaries

**Issue**: A conversation that spans two digest runs will be clustered as two separate conversations across two runs.

**Severity**: Scales inversely with configured cadence — minor at multi-hour cadences, noticeable at short cadences (e.g., 15 min).

**Future fix** (do NOT implement in v1): Persist clusters flagged `likely_continues` across runs and re-include them as context in next run's clustering call. Only build this if real usage shows the problem is severe enough at shortest cadences users actually configure.

### Thin Summaries at Short Cadences

**Issue**: At very short cadences (e.g., 5 min), incremental thread summarization may produce thin summaries like "Mike replied that he agrees" because the NEW set is tiny.

**Mitigation**: This is honest output for "what changed in last 5 minutes" — not a bug.

**Future knob** (do NOT implement now): Minimum-substance threshold on NEW set (e.g., "if NEW set has < 3 substantive messages AND thread already has recent summary, defer to next interval"). Add only if users complain.

### Stale Names After Renames

**Issue**: User display names are cached for 24 hours in Redis. If a user renames themselves, summaries may use old name for up to 24 hours.

**Tradeoff**: This is acceptable. The alternative (no caching) would hammer Slack API on every digest run. The 24-hour TTL is a deliberate balance.

---

## Slack User Name Resolution (Decision Documented)

**Current implementation** (`triage_enrichment.py:161-186`):
- Names cached in Redis with 24-hour TTL (`ex=86400`)
- Key: `slack:user_name:{sender_slack_id}`
- Stored on `TriageClassification.sender_name` at classification time
- Fallback chain: `real_name` → `profile.display_name` → `name` → `sender_slack_id`

**Decision**: Keep as-is. Stale names for 24 hours after rename is acceptable tradeoff vs API rate limit risk.

**Batch resolver**: Added to same file, shares cache key format, fallback chain, and TTL. Single-user resolver refactored to call through batch internally.

---

## Files to Modify/Create

| File | Change |
|------|--------|
| `backend/app/db/models/triage.py` | Add `processed_reason` column |
| `backend/app/db/repositories/triage.py` | Add `mark_processed()` helper |
| `backend/migrations/versions/{next}_add_processed_reason.py` | **CREATE** via autogenerate |
| `backend/app/services/substance_filter.py` | **CREATE** - substance filter with patterns |
| `backend/app/services/triage_enrichment.py` | Add `resolve_user_names_batch()`, refactor single-user resolver |
| `backend/app/services/digest_grouper.py` | Thread context fetch, truncation, first-run detection, LLM clustering |
| `backend/app/services/triage_delivery.py` | Two-mode summarizer, quality prompt with few-shot |
| `backend/app/services/message_clustering.py` | **CREATE** - Phase 2 LLM clustering with partitioning |
| `backend/app/worker/tasks.py` | Wire substance filter, processed_reason marking |
| `backend/tests/services/test_substance_filter.py` | **CREATE** |
| `backend/tests/services/test_digest_grouper.py` | Add thread context, first-run tests |
| `backend/tests/services/test_message_clustering.py` | **CREATE** - Phase 2 clustering tests |
| `backend/tests/services/test_triage_delivery.py` | Add two-mode summarizer, summary quality tests |
| `backend/tests/services/test_triage_enrichment.py` | Add batch name resolution tests |
| `backend/tests/integration/test_digest_flow.py` | Add integration tests with processed_reason assertions |
| `.claude/diagrams/triage-flow.md` | Update with grouping/filtering flow |

---

## Done Means

- [x] All checklist items in Phase 1 marked complete
- [x] Local `pytest` passes (117 tests)
- [x] `uv run ruff check .` clean
- [ ] Manual digest on channel with active multi-message thread produces:
  - [ ] 1 summary (not 8)
  - [ ] Names participants
  - [ ] ≥ 2 sentences
  - [ ] Reflects only NEW messages from current interval (or full thread on first run)
- [ ] Manual digest on channel with standalone emoji/"thanks" produces 0 summaries
- [x] Migration created and run against dev DB
- [x] `triage-flow.md` diagram updated
- [x] Phase 2 checklist items complete
