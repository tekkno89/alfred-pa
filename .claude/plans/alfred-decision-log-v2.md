# PRD v3.2 Decision Log

**Purpose:** Captures the full record of design decisions: original v3 → v3.1 (red-team review), and v3.1 → v3.2 (privacy posture pushback).

---

## Part 1: v3 → v3.1 (Red-team review integration)

[Identical to prior decision log; included here for completeness so this is a single authoritative record.]

### Summary

- **Critical findings (C1–C6):** 5 accepted, 1 modified-and-accepted (C4)
- **Significant findings (S1–S10):** 8 accepted, 2 had nuance (S3, S5)
- **Minor findings (M1–M7):** 5 accepted, 2 reframed (M1 reversed from initial reject; M3 reframed as wording fix)

Net effect: PRD scope is honestly larger than v3 represented.

### Critical findings

**C1. `SenderBehaviorModel` schema mismatch.** Accepted. New `SenderActionDistribution` table added. Existing `SenderBehaviorModel` preserved for response-timing signal.

**C2. R3b requires raw message text that isn't stored.** Accepted with temporary-storage rule. New `SlackMessageCache` (R-Cache), 7-day TTL. Subsequently revised in v3.2 — see Part 2.

**C3. `review` and `digest_summary` states unaccounted for.** Accepted. `review` reframed as orthogonal flag (R-ReviewState), not a fifth action. `digest_summary` becomes a separate `is_consolidated` flag.

**C4. Bot-filter blast radius.** Accepted with architectural answer. R4c revised: bot rules short-circuit before LLM classification. Unified with existing `ChannelSourceExclusion` (renamed `ChannelSourceRule`).

**C5. Always-on vs focus-bounded shift unstated.** Accepted. Two product modes are now Design Principle 9. R3, R5, R7, R8 thread mode-awareness.

**C6. Engagement check excludes notify_now path.** Accepted. R2b's scope explicitly expanded to gate `notify_now` deliveries.

### Significant findings (S1–S10): all accepted.

- **S1.** Escalation/dedup interaction. Solution: `escalation_override = true` flag bypasses dedup.
- **S2.** Retention boundaries. New tables: `SuppressedDelivery` 90 days; `SlackMessageCache` 7 days (revised in v3.2); `FeedbackEmbedding` no time limit (derived data).
- **S3.** `needs_more_context` prototype gate. Revised: cost gate (<25%) + quality gate (measurable accuracy improvement).
- **S4.** Adaptive window convergence. Specified: EMA (α=0.2), per-type bounds, min-5-samples, 50% damping.
- **S5.** Recall metric muddled. Split into classification recall (pre-suppression) and delivery hit rate (post-suppression).
- **S6.** Phantom `ignore_unless_mentioned` column. Cleanup.
- **S7.** Short-ack overlap with `substance_filter`. Extend existing filter rather than build new LLM classifier.
- **S8.** `ChannelSourceExclusion` vs proposed `BotRule`. Unified: extend and rename to `ChannelSourceRule`.
- **S9.** Focus-mode delivery silent change. Made explicit in R5b.
- **S10.** Slack rate limits. Mitigation rewritten: maximize per-call data, aggressive per-digest caching, fall back to stale state with UI indicator.

### Minor findings

- **M1.** `priority` → `action` rename touches 41 files. Initial PM reject; reversed after pushback. Phase 1 estimate inflated; rename treated as own work stream.
- **M2.** R3c precision needs sample threshold. Accepted: minimum-evidence threshold (10 samples).
- **M3.** 15-cap arbitrary. PM rejected; Claude reframed as acceptance criterion ambiguity (active vs archived types). Wording clarified.
- **M4.** DM context size. Accepted: 20 messages, full text in-memory.
- **M5.** R-AwayMode Option 3 references undefined "critical." Deferred.
- **M6.** 10-cap shared between R6 and R8. Accepted: canonical "10 suppressed per user per day" rule.
- **M7.** R-Meta "reasoning" undefined. Accepted: structured fact display, no per-surface LLM calls.

### Net deltas v3 → v3.1

- **New requirements:** R-Cache (universal), R-ReviewState.
- **Renamed:** `ChannelSourceExclusion` → `ChannelSourceRule`.
- **New tables:** `SlackMessageCache`, `SenderActionDistribution`, `FeedbackEmbedding`.
- **Removed:** `BotRule` (unified with `ChannelSourceRule`).
- **Phase 1 estimate:** 2–3 weeks → 3–4 weeks.

---

## Part 2: v3.1 → v3.2 (Privacy posture pushback)

### Trigger

User pushback on storing raw message text universally: *"is there a design that can work just as good without storing the messages in the database?"*

### Four alternatives considered

1. **Option A — embeddings only, never raw text.** Stores derived signals only; sensitive content engagement checks re-fetch from Slack. Strongest privacy posture; loses cross-user efficiency.
2. **Option B — store only corrected messages.** Narrow surface area; works for R3b but not for engagement-check efficiency.
3. **Option C — 24h text TTL, then derived only.** Hybrid; matches operational need but operationally complex.
4. **Option D — v3.1 as written.** 7-day TTL on full text; most permissive.

### Decision sequence

**Q1 — User's primary concern:** Privacy / trust posture. Storing user message text feels like a meaningful posture change.

**Q2 — Deployment context:** Mix of individual users and small teams.

**Q3 — Initial choice:** Hybrid (Option D for channels, embeddings-only for DMs).

**Q4 — Refinement after Claude pressure-test:** User pushed further. Stated they didn't want to store *embeddings* for sensitive content either. Wanted on-demand Slack fetches for all sensitive content, with no derived storage.

**Q5 — Pressure-test of stricter posture:**
- Claude pointed out R3b cannot learn from sensitive content if nothing is stored.
- Claude proposed in-memory-only embedding (compute on the fly per classification).
- User clarified: actually OK storing embeddings as derived data (they're not raw text and enable better learning).
- User clarified: keyword extraction (R3d) for sensitive content is also OK as aggregate per-user data.

**Q6 — Final design choices:**
- Embeddings stored persistently (no time limit) in `FeedbackEmbedding`.
- Topic keywords stored persistently, with source-category tagging for audit.
- Raw text: 7-day cache for non-sensitive only; never for sensitive.
- Per-channel sensitive flag with confirmation dialog for private→non-sensitive downgrades.
- User-facing audit UI for learned data (R-Transparency).

### Why this design wins

**Principled separation:** Persistent storage of *derived signals* (embeddings, keywords, classifications, counts) is permitted. Persistent storage of *raw message text* is heavily restricted (7-day cache for non-sensitive only; never for sensitive). This is qualitatively easier to communicate to users than v3.1's "we cache everything for 7 days."

**Learning consumers preserved:** R3b, R3c, R3d all work for all content types. The only operational cost is more Slack API traffic for sensitive content (engagement checks, escalation, correction-time embedding generation).

**User-facing trust artifact:** R-Transparency lets users see and delete what Alfred has learned. This is the "credible transparency" that makes the derived-data permission feel earned rather than presumptuous.

**Defensible privacy statement:** *"Alfred caches public channel messages for 7 days. We never store the text of your DMs or private channels — we fetch them from Slack only when needed. We do keep aggregate learning data (embeddings, topic keywords) so Alfred can improve, but these don't contain readable message content."*

### Tradeoffs accepted explicitly

- **More operational complexity than v3.1.** Two code paths (cached vs Slack-fetch) everywhere text is needed.
- **More Slack API traffic at delivery time** for heavy DM users.
- **R3b for sensitive content requires Slack fetch at correction time.** Bounded by correction volume.
- **R-Transparency adds ongoing UX maintenance.** Users will delete things and Alfred has to honor that.

### What was rejected from earlier proposals

- **In-memory-only embeddings (no DB persistence).** User reconsidered and was OK with embedding persistence. Avoided this option because it required recomputing embeddings every classification — meaningful compute cost.
- **Skipping R3b entirely for sensitive content.** Earlier discussion considered this; user's final decision to allow derived storage made it unnecessary.
- **No keyword extraction from sensitive content.** Earlier discussion considered this strictest reading. User chose to permit (aggregate per-user data acceptable).
- **Per-channel sensitive flag at Phase 1.** Moved to Phase 3 (with channel sync UI), since the channel sync UI is also Phase 3.

### Net deltas v3.1 → v3.2

**New design principle:**
- **Principle 5 revised:** "Tiered storage with strong privacy defaults."
- **Principle 10 new:** "Transparency over inference."

**New requirements:**
- **R-Transparency:** Learned-data audit UI (view, delete, reset).

**Modified requirements:**
- **R-Cache:** Tiered into cached (non-sensitive public) and on-demand-fetch (sensitive). New `sensitive: bool` flag on `MonitoredChannel`.
- **R3b:** Explicitly works for sensitive content via on-demand Slack fetch at correction time.
- **R3d:** Explicitly works for all content; new `source_category` field on `TopicAffinity` for audit grouping.
- **R4g (channel sync UI):** Per-channel sensitive toggle with confirmation dialog for private→non-sensitive.
- **R-Reliability:** New Slack-fetch reliability note for sensitive content (no silent fallback).

**New services:**
- `SensitiveContentFetcher` — abstraction for on-demand Slack fetching with rate-limit handling.
- `LearnedDataAuditService` — backend for R-Transparency.

**Schema changes:**
- `MonitoredChannel.sensitive` added.
- `TopicAffinity.source_category` added.

**Phase impacts:**
- Phase 1 effort largely unchanged (~3–4 weeks). Tiered cache slightly more complex than universal but the difference is modest.
- Phase 2 adds R-Transparency UI scope.
- Phase 3 adds per-channel sensitive toggle to channel sync UI.

---

## Cumulative Summary (v3 → v3.2)

PRD scope has grown honestly through two rounds of pressure-testing:

- **v3 → v3.1**: Red-team review caught schema mismatches, missed integration assumptions, scope-understated refactors, missing failure modes. PRD became more accurate about what's actually being built.
- **v3.1 → v3.2**: User-led privacy pushback resulted in a tiered storage model that is qualitatively easier to defend than v3.1's universal cache. Adds R-Transparency to make derived-data permission feel earned.

**Net change:** Phase 1 grew from "~2–3 weeks" (v3) to "~3–4 weeks" (v3.1, v3.2). No requirements dropped; meaningful additions in privacy and transparency surfaces.

**What's now hardened:**
- The classification path (action labels, full thread context, walkback, low-confidence review flag).
- The learning path (3 consumers, temporal decay, minimum-evidence thresholds, transparency).
- The delivery path (engagement check across all paths, adaptive timing, focus-mode interaction).
- The reliability path (requeue/backoff, rate-limit fallback, cache cleanup).
- The privacy path (tiered storage, audit UI, sensitive content protection).

**Recommended next step:** Engineering decomposition (Branch A) using v3.2 + this decision log.

---

*End of decision log.*
