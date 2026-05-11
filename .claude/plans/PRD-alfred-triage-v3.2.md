# PRD v3.2: Alfred Slack Triage — Trust & Timing

**Status:** Hardened draft, ready for engineering breakdown
**Owner:** TBD
**Last updated:** 2026-05-10
**Supersedes:** PRD v3.1 (2026-05-10)

> **Changelog from v3.1:** This revision tightens the privacy posture by replacing v3.1's universal message cache with a tiered design (cached for non-sensitive public channels only; sensitive content fetched from Slack on demand). Adds a user-facing learned-keywords audit UI. See `decision-log.md` for full record. Material changes from v3.1 are flagged inline with `[v3.2]` markers.

---

## 1. Problem

Alfred is meant to let users silence Slack and rely on summaries and notifications, freeing them to focus on work. Today, users still peek at channels mid-work because they don't fully trust Alfred's classifications and timing. Two reinforcing failure modes drive this:

1. **Trust gap.** P1/P2 classifications feel inconsistent. Both false positives (interruptions for things that didn't matter) and false negatives (missed things that did matter) occur, and there is no closed feedback loop that improves classification over time. The setup wizard generates static prose definitions that the classifier loosely follows, and existing feedback infrastructure (`TriageFeedback` table) is written to but never consumed.

2. **Timing gap.** Digest delivery is interval/clock based, ignoring whether the user has already engaged with a thread or whether the moment is bad. Even correctly-classified items can land at disruptive moments — and the *anticipation* of a digest is itself an interruption.

These two gaps reinforce each other: distrust of labels causes peeking; once peeking, timing decisions don't matter; chronic peeking trains the user not to rely on Alfred for *anything*, undermining the whole system.

## 2. Goal

Reduce mid-work Slack peeking to near-zero by making Alfred's classifications feel reliably correct and its delivery feel reliably timed. Alfred decides *what* to surface and *when*, and the user trusts both judgments enough to silence Slack without anxiety.

**Success metrics (two distinct measurements):**

- **Classification recall:** ≥90% — of messages the user engaged with, what fraction did Alfred classify as `notify_now` or `summarize_next` (measured pre-suppression).
- **Delivery hit rate:** ≥80% — of `notify_now` items actually delivered (post-suppression by engagement check), what fraction did the user engage with.

Both measured within 4 weeks of usage. Onboarding suppression rules apply (see R7).

## 3. Non-goals

- Replacing focus mode. This work *enables* focus-mode adoption by building trust; it does not subsume it.
- Cross-app triage (calendar, email). Slack only.
- Full PTO catch-up feature. Away-mode primitives are introduced here (R-AwayMode), but calendar-driven detection and the catch-up summary itself ship later.
- Cross-channel deduplication. Acknowledged as a real edge case but explicitly out of scope.

## 4. Design Principles

1. **Action over taxonomy.** The classifier outputs an *action* (what Alfred should *do* with this message), not an abstract priority level. P0–P3 survives as a UI display layer.
2. **No ambient cues.** No queue indicators, no "things waiting" badges, no peripheral signals.
3. **Conversation is the unit.** Threads and DM histories are the primitive for classification and engagement state, not individual messages.
4. **Engagement is dispositive.** If the user has reacted or replied substantively, that conversation/message is closed from Alfred's perspective.
5. **Tiered storage with strong privacy defaults [v3.2: revised].** Persistent storage of derived signals (embeddings, topic keywords, classifications, counts) is acceptable. Persistent storage of raw Slack message text is restricted: cached only for public, non-sensitive channels with a 7-day TTL; never stored for DMs, private channels, or user-flagged sensitive channels. Sensitive content is fetched from Slack on demand.
6. **Learned settings show their reasoning.** Every adaptive value surfaces both its current state and the structured facts behind it.
7. **Per-user everything.** This is a multi-user system. Per-user data is scoped per-user, even when users share a workspace. The message cache (R-Cache) is the explicit exception: workspace-scoped and shared for non-sensitive content.
8. **Reliability over speed.** Failed engagement checks or classification calls requeue with backoff.
9. **Two product modes.** Alfred operates in either *always-on* (continuous classification) or *focus-bounded* (classification active only during focus sessions). Several requirements behave differently between modes.
10. **[v3.2: new] Transparency over inference.** Users can see what Alfred has learned about them (topic affinity keywords, learned rules) and delete or correct it. Aggregate signals are not opaque.

## 5. Glossary

- **Action label.** One of `notify_now`, `summarize_next`, `summarize_eod`, `ignore`. Internal primitive output by classification.
- **`review` state.** An orthogonal flag (not a fifth action) indicating low-confidence classification deferred to the user.
- **Message type.** A user-defined or Alfred-suggested category. Per-user.
- **Engagement.** A user reaction (any emoji) or substantive reply on a message or thread.
- **Substantive reply.** Any reply that is not a short acknowledgment. Determined by `substance_filter` extended for the user-reply case.
- **Walkback.** Bounded fetching of additional channel history to provide more context to the classifier.
- **Counterfactual review.** End-of-day check on conversations that resolved without the user.
- **Suppressed delivery.** A queued item that was dropped before delivery because the user engaged or the conversation resolved.
- **Always-on / focus-bounded.** The two product modes.
- **Message cache.** The workspace-scoped, 7-day-TTL store of raw Slack message text used for non-sensitive public-channel content.
- **[v3.2: new] Sensitive content.** Any message from a DM, private channel, or user-flagged sensitive channel. Raw text is never persisted; fetched from Slack on demand.
- **[v3.2: new] Derived signal.** Any data computed from raw text but not containing raw text: embeddings, topic keywords, classifications, action distributions. Persistent storage permitted for all channel types.

---

## 6. Requirements

### R1. Action-based classification

The classifier outputs one of four actions:

| Action | Meaning | Delivery |
|---|---|---|
| `notify_now` | Interrupt as soon as possible | Immediate push |
| `summarize_next` | Bundle into next reasonable digest | Context-triggered delivery (R5) |
| `summarize_eod` | Include in end-of-day rollup | Daily digest at configured time |
| `ignore` | Don't surface in any form | Suppressed entirely |

Plus an orthogonal `review` flag for low-confidence classifications.

**Display layer.** Users see "P0 / P1 / P2 / P3" if they prefer (P0=`notify_now`, P1=`summarize_next`, P2=`summarize_eod`, P3=`ignore`).

**No deterministic pre-filter.** All non-trivial messages are classified by LLM.

**Hardcoded `ignore` rule.** `@here`, `@channel`, `@everyone` mentions deterministically classified as `ignore` without an LLM call.

**`priority` → `action` rename is its own work stream.** Counted: 25 backend Python files + 16 frontend files reference `priority` or `priority_level`. Dedicated 3–4 day ticket within Phase 1 with regression tests.

**Migration:**

| Existing value | Maps to |
|---|---|
| `p0` | action: `notify_now` |
| `p1` | action: `summarize_next` |
| `p2` | action: `summarize_eod` |
| `p3` | action: `ignore` |
| `review` | best-guess action + `review` flag = true |
| `digest_summary` | underlying action + `is_consolidated` flag = true |

**Acceptance criteria:**
- [ ] All classifier outputs use action labels internally; P0–P3 is a UI-only display.
- [ ] `priority` → `action` rename completes as a dedicated work stream with regression tests.
- [ ] Wizard prompts include "what messages should Alfred ignore" as a first-class question.
- [ ] Per-channel and per-sender rules can target any of the four actions.
- [ ] `@here` / `@channel` / `@everyone` deterministically classified as `ignore` with no LLM call.
- [ ] Migration script handles all six existing `priority_level` values without data loss.

---

### R-Cache. Tiered message storage *[v3.2: substantially revised]*

A workspace-scoped cache of raw message text for non-sensitive public channels only. Sensitive content is fetched from Slack on demand.

#### R-Cache.a. Sensitive flag on monitored channels

New column on `MonitoredChannel`: `sensitive: bool`.

**Defaults:**
- **Public channels:** `sensitive = false` (cached per R-Cache.b).
- **Private channels:** `sensitive = true` (no caching; fetch from Slack on demand).
- **DMs:** always `sensitive = true`, NOT user-toggleable. Hardcoded behavior.

**User control (in channel sync UI, per R4g):**
- Public channel → mark as sensitive: one-click, no warning.
- Private channel → downgrade to non-sensitive: requires confirmation dialog with warning: *"This is a private channel. Disabling sensitive mode means Alfred will cache message text from this channel for up to 7 days to improve performance. Continue?"* User must actively confirm.

#### R-Cache.b. Cache schema (public, non-sensitive channels only)

Table: `SlackMessageCache`

| Column | Type | Notes |
|---|---|---|
| `workspace_id` | string | Slack team ID |
| `channel_id` | string | Channel ID (not used for DMs) |
| `message_ts` | string | Slack message timestamp |
| `parent_thread_ts` | string, nullable | For thread replies |
| `sender_slack_id` | string | |
| `text` | text | Raw message text |
| `is_bot` | bool | |
| `created_at` | timestamp | Slack message timestamp (parsed) |
| `cached_at` | timestamp | Local insert time, indexed for TTL cleanup |

Primary key: `(workspace_id, channel_id, message_ts)`. Index on `(parent_thread_ts)`. Index on `cached_at`.

**Behavior:**
- Shared across users. Multiple users monitoring same channel reference same cache rows.
- Populated on first need. Cache-miss triggers Slack fetch and persist.
- **TTL: 7 days.** Nightly cleanup job deletes expired rows.

#### R-Cache.c. Sensitive content path

For all sensitive content (DMs, private channels, user-flagged channels):

- **No text persistence whatsoever.** Text exists only in memory during classification, engagement check, escalation, or correction.
- **R2b engagement check** fetches from Slack at delivery time. Rate-limit fallback to "stale state" with UI indicator under sustained pressure.
- **R2c escalation** fetches from Slack when escalation patterns trigger. Bounded by escalation trigger volume.
- **R3b correction-time embedding:** When user corrects a sensitive-content classification, the service fetches the message from Slack, computes the embedding, stores the embedding (in `FeedbackEmbedding`), discards the text. Single extra Slack API call per sensitive-content correction.

**Operational note:** Sensitive content imposes meaningfully more Slack API traffic than v3.1's universal cache design. The tradeoff is explicit and worth it for privacy posture.

**Acceptance criteria:**
- [ ] `MonitoredChannel.sensitive` column added with correct defaults per channel type.
- [ ] Public channels default to cached; private channels default to non-cached.
- [ ] DM messages never persisted; always fetched on demand.
- [ ] User can flag any public channel as sensitive (one-click); private channels require confirmation to downgrade.
- [ ] `SlackMessageCache` populated only for non-sensitive content.
- [ ] All services querying for text check `sensitive` flag first: cache-first for non-sensitive, Slack-fetch for sensitive.
- [ ] Nightly cleanup removes expired cache rows.
- [ ] Per-message Slack API calls drop measurably on shared non-sensitive channels (target: ≥50% reduction in test environment).

---

### R-ReviewState. Orthogonal `review` flag for low-confidence classifications

`review` is not a fifth action — it's a flag indicating the classifier had low confidence.

**Behavior:**
- Triggered when classification `confidence < threshold` AND no fallback rule provides a clear action.
- Classification still produces a best-guess action (so the message has a fallback delivery path).
- Review queue items appear in R6's "needs your call" section.
- User's "should be" answer is a strong correction signal (same weight as explicit correction in R3).
- Items with `review = true` are still delivered per best-guess action.

**Acceptance criteria:**
- [ ] `review` is a boolean column on `TriageClassification`.
- [ ] Low-confidence classifications get `review = true` and a best-guess action.
- [ ] R6 includes a "needs your call" section.
- [ ] User responses propagate to R3 as strong corrections.

---

### R2. Conversation-aware classification & delivery

#### R2a. Context fetching

**Threads.** Fetch entire thread for classification. Source:
- Non-sensitive: cache-first per R-Cache.
- Sensitive: Slack-fetch on demand (no cache).

**Channel messages (non-threaded).** Default context: last 5 messages of channel history.

Walkback engages when needed:
- Classifier output includes `needs_more_context: bool` and `confidence: float`.
- If `needs_more_context == true` AND confidence below threshold, fetch next 10 messages back.
- **Hard cap: 2 walkbacks total** (5 → 15 → 25 messages).
- **Time cap:** no messages older than 2 hours.

**DMs.** Last 20 messages of context in-memory. No persisted truncation (DMs are sensitive; never cached).

**Prototype gate for walkback:**
- Walkback fires on < 25% of classifications (cost gate).
- Walkback produces measurable classification accuracy improvement (quality gate).
- Both must pass to ship. Spike: ~1–2 days.

#### R2b. Engagement check at delivery

Engagement check gates **all** delivery paths — `notify_now`, `summarize_next`, and `summarize_eod`.

Wired into:
- `triage_pipeline._deliver_urgent` (the `notify_now` path)
- `triage_delivery` (the digest paths)
- All future delivery surfaces

**Suppression triggers (within 3-day window):**
- **Any reaction** on a message → that message ineligible.
- **Substantive reply** in thread/DM → all messages up to and including the reply ineligible. Messages after the reply classified independently.
- **Short-acknowledgment reply** → only the message being directly replied to is ineligible.

**Short-ack detection:** Uses existing `substance_filter.py` extended to operate on user replies. LLM-based ack classifier deferred as fast follow.

**Reactions handling:** Wire up `reactions.get` in `DigestResponseChecker` (currently not called despite `reactions:read` scope granted).

**Engagement-check time window:** 3 days.

**Rate-limit handling:**
- Per-user-token tier limits apply per-user, so parallelization within a digest doesn't help.
- Use `conversations.replies` with `limit` parameter to maximize per-call data.
- Aggressively cache `(thread_id, fetch_window)` per digest assembly.
- Under sustained rate-limit pressure: fall back to classification-time engagement state with UI indicator on affected items.

**Sensitive content note:** All engagement checks on DMs and private channels go through Slack fetches. Heavy DM users will see meaningfully more Slack API traffic at delivery time than non-sensitive-heavy users. The rate-limit fallback applies equally.

#### R2c. Escalation detection

**Pattern stage triggers:**
- Same sender pings 2+ times within N minutes (suggested 5 min).
- Sender pings, then adds @-mention to user.
- Thread accelerates (≥5 new messages in 10 min on a thread user has not engaged with).

**Content stage gate.** If pattern stage triggers, re-classify with full updated context (fetched from cache for non-sensitive, from Slack for sensitive). Promote to `notify_now` only if new classification confirms content matches user signals.

**Cold-start fallback.** When learned signals are empty:
- Escalation fires *only* if (a) channel's baseline floor is `notify_now` or `summarize_next` AND (b) message contains direct @-mention or DM signal.

**Deduplication interaction.** The existing `AlertDeduplicationService` suppresses alerts when same thread/sender has been alerted within 30 min. Escalation pushes bypass dedup via `escalation_override = true` flag.

**Direction.** Escalation can only promote `summarize_next` → `notify_now`.

**Acceptance criteria:**
- [ ] Threaded messages classified with full thread context.
- [ ] Walkback prototype validated against both cost and quality gates.
- [ ] Classifier output includes `needs_more_context` and `confidence` fields.
- [ ] Engagement check gates `notify_now`, `summarize_next`, AND `summarize_eod` paths.
- [ ] Reactions observed (new `reactions.get` integration).
- [ ] Short-ack detection via extended `substance_filter`.
- [ ] Engagement-check time window: 3 days.
- [ ] Rate-limit fallback to stale state with UI indicator.
- [ ] Escalation detector runs as worker job with content gate and cold-start fallback.
- [ ] Escalation pushes bypass `AlertDeduplicationService` via override flag.
- [ ] Sensitive content engagement checks documented as Slack-fetch-only path.

---

### R3. Closed-loop learning (three consumers)

#### R3a. Feedback capture

One-tap correction on every digest item and `notify_now` push: ✓ / ↑ / ↓ with optional one-line "why."

Implicit signals:
- `summarize_eod` items user doesn't engage with → soft negative.
- `summarize_next` items user engages with quickly → positive.
- Suppressed deliveries flagged in counterfactual review (R8).
- User responses to `review`-flagged items → strong corrections.

#### R3b. Consumer 1: Few-shot retrieval *[v3.2: works for all content, including sensitive]*

For each new classification, retrieve top-K (K=5) most semantically similar past corrections from the same channel and sender. Inject as few-shot exemplars in classifier prompt.

**Embedding lifecycle:**
- At correction time: service obtains message text (from cache for non-sensitive, from Slack fetch for sensitive), computes embedding, stores embedding in `FeedbackEmbedding`, discards text reference.
- At classification time: service queries `FeedbackEmbedding` by similarity to the new message's embedding; retrieves top-K matches.

**`FeedbackEmbedding` table:** `(triage_feedback_id, embedding_vector, computed_at)`. Embeddings persist beyond the 7-day cache TTL since they are derived data with no raw text retention.

**Sensitive content support:** R3b works for sensitive corrections via the on-demand Slack fetch at correction time. One extra Slack API call per sensitive-content correction. Acceptable volume (corrections are bounded user-initiated events).

**Sequencing:** R3b depends on R-Cache being live (for the non-sensitive path) and on the `reactions.get` + Slack fetch infrastructure (for the sensitive path).

#### R3c. Consumer 2: Per-(sender, channel) action distribution

New table: `SenderActionDistribution`

| Column | Type | Notes |
|---|---|---|
| `user_id` | FK | |
| `sender_slack_id` | string | |
| `channel_id` | string | |
| `action_distribution` | JSON | Distribution over four actions |
| `sample_count` | int | |
| `last_computed_at` | timestamp | |

Existing `SenderBehaviorModel` preserved as-is for response-timing signal.

Nightly worker job derives, for each (user, sender, channel) triple, the historical distribution of corrected actions with 30-day half-life decay.

**Works for all content** — counts and labels, no text needed.

**Minimum-evidence threshold:** Don't surface distribution-based reasoning unless `sample_count ≥ 10`. Below threshold, fall back to topic affinity or few-shot. UI shows "still learning."

#### R3d. Consumer 3: Topic affinity (per-user) *[v3.2: works for all content, with audit UI]*

**Phase 2 implementation: keyword-based.**

At classification time (text in memory): LLM extracts topical keywords from the message. At correction time (positive signal): same. Stored as user-specific keyword lists with weights.

**Works for all content** — keyword extraction happens in-memory at classification time when text is available. No raw text persisted; only the extracted keywords (aggregate per-user derived data).

At classification time, message keywords compared against user's affinity lists; bias passed to classifier prompt.

**Audit UI [v3.2: new per Principle 10]:** Users can view all learned topic keywords in a settings page. Each keyword shows:
- The keyword itself.
- Weight (positive/negative).
- Source channel categories (e.g., "from public channels," "from sensitive channels").
- Last updated timestamp.

Users can delete individual keywords (one-click) or bulk-delete by category. Deleted keywords are not re-learned until new explicit signal arrives.

**Temporal decay:** 30-day half-life.

**Phase 4 (deferred):** Upgrade to embedding-based topic centroids if keyword approach proves imprecise.

#### R3e. Pattern suggestions

After 5+ corrections matching a recognizable pattern, Alfred surfaces a rule suggestion in the end-of-day review. One-tap accept or dismiss.

**Acceptance criteria:**
- [ ] One-tap correction controls on every digest item and notify-now push.
- [ ] `LearnedExampleRetriever` deployed and consumed by classifier prompt.
- [ ] `FeedbackEmbedding` table stores derived embeddings; no time limit on retention.
- [ ] **[v3.2] R3b works for sensitive content via on-demand Slack fetch at correction time.**
- [ ] New `SenderActionDistribution` table; `SenderBehaviorModel` preserved.
- [ ] Nightly job computes and writes action distributions with 30-day decay.
- [ ] Minimum-evidence threshold (10 samples) enforced before R3c reasoning surfaces.
- [ ] Topic-affinity keyword extraction and bias injection working.
- [ ] **[v3.2] Topic affinity works for all content types (sensitive and non-sensitive).**
- [ ] **[v3.2] Learned-keywords audit UI: view, delete individual, bulk-delete by category.**
- [ ] Pattern-suggestion job runs on regular cadence.
- [ ] Within 2 weeks of use, classification reasoning visibly cites learned signals.

---

### R4. Structured channel & message-type rules

#### R4a. Per-user message types

Message types per-user: `(user_id, type_name, type_definition, source)`.

**Wizard onboarding:** Role-based starter type sets (Engineering, Sales, Management, Design, Product, Operations, Other). Multi-select supported.

**Custom types.** Users can create from scratch.

**Alfred-suggested types.** After ≥5 messages in a cluster that don't fit existing types, propose new type. Surfaces in weekly review.

**Cap:** Hard cap of 15 active (non-archived) types per user. Archived types do not count.

#### R4b. Per-channel type→action rules

Per-(user, channel, type) action mapping.

#### R4c. Bots as first-class senders

**Phase 1 prerequisite:** Investigate why current code globally filters bot messages and what broke in focus mode when disabled. Acceptance criterion: focus mode behaves identically before and after bot-filter changes.

**Architectural design:**
1. Bot rules short-circuit BEFORE LLM classification.
2. Default rule for unconfigured bots: `ignore`. Users opt-IN to attention.
3. Unification with existing `ChannelSourceExclusion`: extend and rename to `ChannelSourceRule`. Migrate existing rows.

#### R4d. Mention-type structured signals

- `@user_directly` — strong priority bump.
- `@here`, `@channel`, `@everyone` — filtered to `ignore`.
- `@usergroup_user_belongs_to` — moderate signal.

#### R4e. VIP senders (manual override only)

User manually marks senders as VIP. VIP senders floored at `summarize_next`.

#### R4f. "Things have changed" reset affordance

User-triggerable: triggers fresh wizard pass, 50% decay on pre-reset corrections, prompts to review existing rules.

#### R4g. Channel sync UI *[v3.2: extended with sensitive flag]*

Preserved: sync from Slack → user selects channels → user sets baseline priority floor.

**[v3.2: new]** Per-channel `sensitive` toggle:
- Public channels: shown with default `sensitive = false`; user can toggle on (one-click).
- Private channels: shown with default `sensitive = true`; user can toggle off only via confirmation dialog with warning text.
- DMs: not displayed in channel sync (always sensitive, not user-toggleable).

Plus: channel-intelligence view, volume indicator (noisy / moderate / quiet).

**Acceptance criteria:**
- [ ] Message types per-user; multi-role wizard supported.
- [ ] Type→action rules table.
- [ ] Bot-filter focus-mode investigation completed; behavioral parity verified.
- [ ] Bot rules short-circuit before LLM classification; default action is `ignore`.
- [ ] `ChannelSourceExclusion` extended/renamed; migration preserves existing data.
- [ ] Mention-type signals passed to classifier.
- [ ] VIP sender manual override exists.
- [ ] "Things have changed" reset works end-to-end.
- [ ] **[v3.2] Channel sync UI includes per-channel sensitive toggle with correct defaults and confirmation dialogs.**
- [ ] Channel sync UI extended with intelligence view and volume indicator.

---

### R5. Smart delivery

`digest_scheduler.py` reframed as `DigestDeliveryOrchestrator` with pluggable triggers.

#### R5a. `notify_now` delivery

Immediate push (subject to R-AwayMode and engagement check per R2b).

**Auto-degrade:** `notify_now` items not engaged with within user-configurable timeout (default 4 hours) auto-degrade to summary entry.

#### R5b. `summarize_next` delivery

Triggers, in order:
1. **End-of-meeting.** Calendar event ends, no immediate next event.
2. **Idle detection.** Slack presence `away` for ≥10 min, OR no calendar event currently active and last event ended >15 min ago.
3. **Escalation push (R2c).** Promoted to `notify_now`, pushed immediately.
4. **Stale-queue ceiling.** Per-type window reaches limit.

**Focus mode interaction:**
- **Focus-bounded mode:** no `summarize_next` deliveries during focus sessions. Items queue.
- **Always-on mode:** focus suppresses non-escalation deliveries. Escalation pushes continue during focus.

No clock-interval delivery for `summarize_next` beyond per-type backstop.

#### R5c. Per-type adaptive delivery windows

Each `(user, message_type)` pair has a target delivery window.

**Starter values:**

| Type | Starter window |
|---|---|
| `pr_review_request` | 30 min |
| `direct_question` | 30 min |
| `mention` | 30 min |
| `discussion_relevant_to_my_work` | 60 min |
| `announcement` | end-of-day |
| `informational` | end-of-day |

**Adaptive learning:**
- EMA update rule, α = 0.2.
- Per-type floor and ceiling.
- Minimum 5 engagements before adjustment.
- Damping: single engagement cannot shift window by more than 50% of current value.

#### R5d. `summarize_eod` delivery

Single daily digest at user-configured time (default 5:30pm local).

#### R5e. `ignore` delivery

Suppressed entirely.

**Acceptance criteria:**
- [ ] No clock-interval delivery for `summarize_next` except per-type backstop.
- [ ] Calendar integration wired into delivery triggers.
- [ ] Engagement check gates `notify_now`.
- [ ] Focus mode suppresses non-escalation deliveries in both product modes.
- [ ] Per-type windows configurable with adaptive learning.
- [ ] Per-type window UI surfaces current value, reasoning, "still learning" framing.
- [ ] `notify_now` auto-degrade after configurable timeout.

---

### R6. End-of-day review

Single screen, daily, at user-configured time. Target: <2 minutes.

**Sections:**
1. **Action items still pending.** `summarize_next` items not engaged with during the day.
2. **Counterfactual review (R8).** Conversations that resolved without the user. Capped at canonical "10 suppressed items per user per day."
3. **"Needs your call."** Items flagged `review = true` for low-confidence classifications.
4. **Spot check.** Random sample of 5 `ignore` and 5 `summarize_eod` items.
5. **Pattern suggestions** from R3e.

**Acceptance criteria:**
- [ ] User-configurable clock time (default 5:30pm local).
- [ ] All five sections present.
- [ ] Single-screen UI; review takes <2 min.
- [ ] Counterfactual and auto-promotion share canonical 10-item cap.
- [ ] Review-state items propagate user decisions to R3 as strong corrections.

---

### R7. Trust telemetry — split metrics

#### Classification recall

Of messages the user engaged with, what fraction did Alfred *classify* (pre-suppression) as `notify_now` or `summarize_next`?

**Target after onboarding: ≥90%.**

#### Delivery hit rate

Of `notify_now` items *delivered* (post-suppression), what fraction did user engage with?

**Target after onboarding: ≤20% wasted (≥80% engagement on delivered items).**

**Onboarding state.** Both shown as "still learning" until first of: N days elapsed (default 14) OR ≥50 corrections received.

**Two-mode behavior:**
- Always-on: computed as above.
- Focus-bounded: denominator restricted to "messages user engaged with that arrived during classification-active window."

**Acceptance criteria:**
- [ ] Both metrics computed daily.
- [ ] Onboarding state suppresses display until threshold reached.
- [ ] Focus-bounded mode metrics restrict to in-focus messages.
- [ ] No new data captured beyond user-token scope.

---

### R8. Counterfactual review (suppressed-delivery loop)

When R2b suppresses a delivery, the suppressed item is recorded.

**Behavior:**
1. `SuppressedDelivery` table: `(user_id, message_id, original_action, suppression_reason, outcome_summary, user_review_response, created_at)`.
2. Default auto-promotion: suppressed `summarize_next` item auto-included in next end-of-day digest.
3. **Canonical cap: 10 suppressed items per user per day**, newest first. Shared with R6.
4. R6's counterfactual section: "would you have wanted to know sooner?"
5. "Yes" answers feed R3 as strong positive signal.

**Retention:** 90 days.

**Acceptance criteria:**
- [ ] `SuppressedDelivery` populated by R2b suppression.
- [ ] Auto-promotion at canonical cap.
- [ ] Counterfactual review section in R6.
- [ ] "Yes" responses propagate to R3.
- [ ] 90-day retention.

---

### R-AwayMode. Manual away mode

Manual on/off toggle. Calendar integration ships later with full PTO catch-up.

**Per-user behavior options for `notify_now` while away:**
1. Push immediately (default).
2. Queue for catch-up summary.

Option 3 ("push only if critical") deferred until critical-flag concept is fully specified.

**Catch-up summary** delivered when away mode toggles off.

**Acceptance criteria:**
- [ ] Manual toggle exists.
- [ ] User can configure `notify_now` behavior while away (Options 1 and 2 only).
- [ ] Queued items deliverable as single catch-up digest on toggle off.
- [ ] Data model supports calendar-driven activation when added later.

---

### R-Reliability. Delivery and classification reliability

Failed engagement checks or classification calls requeue with backoff.

**Engagement-check failure:** 30s → 2min → 10min → 1hr → alert ops. Under sustained rate-limit pressure, fall back to "classification-time engagement state" with UI indicator.

**LLM classification failure:** Same backoff. Never default-classify on failure.

**Persistent failure:** Surface "delivery delayed" on next user interaction.

**Cache cleanup reliability.** TTL cleanup job monitored. Failures alert ops within 48 hours.

**[v3.2: new] Slack-fetch reliability for sensitive content.** Since sensitive content has no cache fallback, Slack API failures during engagement check or escalation propagate to the requeue policy. No silent fallback to cached stale data is available; the rate-limit "stale state with UI indicator" path applies (using classification-time state).

**Acceptance criteria:**
- [ ] Backoff retry policy for engagement and classification failures.
- [ ] Persistent failure surfaced to user on next interaction.
- [ ] Cache cleanup monitored.
- [ ] **[v3.2] Slack-fetch failures for sensitive content honor requeue policy; no silent fallback.**

---

### R-Meta. Learned settings show their reasoning

Structured fact display (deterministic, no LLM calls per surface).

**Example:**
> **Sender:** @raj
> **Past corrections:** 9 / 12 → summarize_next (last 30 days)
> **Channel rule:** pr_review_request → summarize_next
> **Confidence:** above minimum-evidence threshold (10+ samples)

**Applies to:**
- Per-type delivery windows.
- Channel type→action rules (when Alfred-suggested).
- Per-(sender, channel) action distributions.
- Topic affinity (positive/negative keyword lists with sample evidence).
- Pattern suggestions.

"Still learning" framing below threshold.

**Acceptance criteria:**
- [ ] All adaptive settings surface current value and structured reasoning.
- [ ] All adaptive settings include "still learning" framing below threshold.
- [ ] No LLM calls per surfaced setting.

---

### R-Transparency. Learned-data audit UI *[v3.2: new]*

Per Principle 10, users can view and delete what Alfred has learned about them.

**Surfaces:**

1. **Topic affinity keywords** (R3d):
   - Settings page showing all learned keywords with weight, source channel category, last updated.
   - One-click delete per keyword.
   - Bulk delete by source channel category ("delete all keywords learned from sensitive channels").
   - Deleted keywords not re-learned until new explicit signal arrives.

2. **Per-(sender, channel) action distributions** (R3c):
   - View per-sender learned distributions in sender detail view.
   - One-click reset per (sender, channel) pair.

3. **Per-type delivery windows** (R5c):
   - View current values with reasoning.
   - One-click reset to default per type.

4. **Pattern suggestions accepted/dismissed history**: viewable, individual rules deletable.

**Out of scope for this PRD:** GDPR-style bulk-export of all derived data. Worth doing eventually but not blocking.

**Acceptance criteria:**
- [ ] Topic keywords audit UI with view, individual delete, bulk delete by category.
- [ ] Action distributions resetable per (sender, channel).
- [ ] Per-type delivery windows resetable.
- [ ] Pattern suggestion history viewable and deletable.

---

## 7. Sequencing

| Phase | Items | Rough effort | Why this order |
|---|---|---|---|
| **Phase 1** | R1 (action labels, no pre-filter, @here/@channel filter, **priority→action rename as work stream**) + R2a/b (full thread fetch, walkback, simplified engagement check, **gates notify_now**) + **R-Cache (tiered: cache for non-sensitive, on-demand fetch for sensitive)** + R-ReviewState + R-Reliability + Bot-filter focus-mode investigation | **~3–4 weeks** | Foundation. Engagement check is trust quick win. R-Cache prerequisite for R3b. Rename is its own work stream. Tiered cache adds modest complexity vs v3.1's universal cache but pays for itself in privacy posture. |
| **Phase 2** | R3 (3 learning consumers + temporal decay + minimum-evidence threshold + **new `SenderActionDistribution`**, **R3b works for sensitive content via on-demand fetch**) + R8 (counterfactual review) + R6 (eod review) + R7 (split telemetry) + R-Meta + **R-Transparency (learned-keywords audit UI)** | **~3 weeks** | Trust-building bundle. R3b depends on R-Cache being live. R-Transparency lands here since all learned signals start being computed. |
| **Phase 3** | R4 (role-based starter types, per-user types, **bot rule layer, `ChannelSourceRule` unification**, manual VIP override, "things changed" reset, mention-type signals, **per-channel sensitive toggle in channel sync UI**, channel intelligence view) + R2c (escalation with content gate + cold-start fallback + dedup override) | ~2 weeks | Once feedback flows, patterns surface and codify. Bots ship here post-investigation. Per-channel sensitive flag UI lives here. |
| **Phase 4** | R5 (smart delivery, per-type adaptive windows, notify_now auto-degrade, explicit focus-mode interaction) + R-AwayMode (manual toggle, Options 1 & 2 only) | ~2 weeks | Timing optimization last. Away mode primitives ship here. |

**Critical sequencing notes:**

- **Phase 1's biggest risks are the priority→action rename and the tiered R-Cache.** 41-file rename + new tiered cache infrastructure is real work. Both have implications for everything downstream.
- **R-Cache must land early in Phase 1.** R3b cannot ship without it. The tiered design adds complexity vs a universal cache, but the privacy gain is the reason for v3.2's existence.
- **The focus-mode investigation must complete before Phase 3 bot work.** Acceptance: behavioral parity.
- **Two product modes thread through R3, R5, R7, R8.** Implement mode-awareness as a top-level concern in Phase 2.

---

## 8. Refactor implications

**`backend/app/services/triage_classifier.py`:**
- Output schema: replace `priority` with `action`; add `confidence`, `needs_more_context`, `message_type`, `reasoning_signals`, `review` flag.
- Prompt construction accepts: few-shot exemplars, per-(sender, channel) distribution, per-user topic-affinity, structured mention signals.

**`backend/app/services/triage_pipeline.py`:**
- Walkback logic added.
- Engagement-check gate before `_deliver_urgent` (notify_now path), not just digest paths.

**`backend/app/services/triage_enrichment.py`:**
- Cache-first for non-sensitive content; Slack-fetch-only for sensitive content.
- Existing thread-context logic refactored to query `MonitoredChannel.sensitive` flag before deciding cache vs Slack.

**`backend/app/services/triage_router.py`:**
- Bot-rule short-circuit added before LLM classification path.
- Bot rules query renamed `ChannelSourceRule` table.
- Focus-mode investigation prerequisite before bot-filter removal.

**`backend/app/services/digest_scheduler.py` → `digest_delivery_orchestrator.py`:**
- Pluggable triggers: calendar-end, idle, escalation, stale-queue ceiling, end-of-day.
- Explicit focus-mode interaction logic.

**`backend/app/services/digest_response_checker.py`:**
- Canonical engagement-check gate for *all* delivery paths including notify_now.
- New `reactions.get` integration.
- Short-ack detection via `substance_filter` extension.
- Rate-limit fallback with UI indicator.
- 3-day engagement window.
- Cache-first for non-sensitive; Slack-fetch-only for sensitive.
- `EngagementMatchTelemetry` logging.

**`backend/app/services/substance_filter.py`:**
- Extended to operate on user replies.

**`backend/app/services/alert_deduplication.py`:**
- Respect `escalation_override` flag.

**`backend/app/services/triage_wizard.py`:**
- Role-based starter type sets; multi-select.

**New services:**
- `SlackMessageCache` (workspace-scoped, non-sensitive only).
- `LearnedExampleRetriever`.
- `EscalationDetector`.
- `EngagementMatchTelemetry`.
- `SuppressedDeliveryService`.
- `TopicAffinityService`.
- `MessageCacheCleanupJob`.
- **[v3.2] `SensitiveContentFetcher`** — abstraction for on-demand Slack fetching of sensitive content with rate-limit handling.
- **[v3.2] `LearnedDataAuditService`** — backend for R-Transparency (view, delete, reset).

**Data model changes:**

| Table | Change |
|---|---|
| `SlackMessageCache` | NEW. Public, non-sensitive channels only. 7-day TTL. |
| `MonitoredChannel` | **[v3.2]** Add `sensitive: bool` with correct defaults per channel type. |
| `MessageType` | NEW. |
| `ChannelTypeRule` | NEW. |
| `ChannelSourceRule` | Extended from `ChannelSourceExclusion`. |
| `VipSender` | NEW. |
| `TopicAffinity` | NEW. `(user_id, keyword, weight, source_category, last_updated)`. **[v3.2]** `source_category` field added to support audit UI. |
| `SuppressedDelivery` | NEW. 90-day retention. |
| `SenderActionDistribution` | NEW (separate from preserved `SenderBehaviorModel`). |
| `SenderBehaviorModel` | Preserved as-is. |
| `FeedbackEmbedding` | NEW. Persists beyond R-Cache TTL. |
| `TriageClassification` | Rename `priority_level` → `action`; add `confidence`, `message_type_id`, `needs_more_context`, `review` flag, `is_consolidated` flag. |
| `TriageFeedback` | Add indexed `(user_id, sender_slack_id, channel_id, created_at)`. |
| `TriageUserSettings` | Add `eod_review_time`, `notify_now_degrade_minutes`, `away_mode_enabled`, `away_mode_notify_now_behavior`, `product_mode`. |
| `EngagementMatchLog` | NEW. |

---

## 9. Tradeoffs

- **Phase 1 is bigger than v3 originally specified.** ~3–4 weeks. The priority→action rename, R-Cache (now tiered) infrastructure, and engagement-check expansion add real work.
- **Tiered storage adds operational complexity vs v3.1's universal cache.** Two code paths (cached vs on-demand Slack fetch). The privacy gain justifies it. The cost is more conditional logic everywhere text is needed.
- **Sensitive content imposes meaningful Slack API traffic** at delivery time, correction time, and escalation time. Heavy DM users will see noticeably more API calls than non-sensitive-heavy users. Rate-limit fallback is the safety net.
- **R3b for sensitive content requires Slack fetch at correction time.** Single API call per sensitive correction. Bounded by user-initiated correction volume.
- **Storage of derived signals is permitted; storage of raw text is not (except 7-day cache for non-sensitive).** This is a real privacy posture: defensible, narrow, and communicable.
- **Conversation context doubles prompt size on threaded messages.**
- **Per-sender models bias toward past behavior.** 30-day half-life decay mitigates.
- **Type taxonomy is opinionated at start.** Role-based starter sets editable.
- **No deterministic pre-filter** means LLM cost on chatty channels.
- **`needs_more_context` self-report is a calibration bet.** Phase 1 prototype validates against cost + quality gates.
- **R3b sequencing depends on R-Cache.**
- **R3c minimum-evidence threshold** means many (sender, channel) pairs will never surface distribution reasoning.
- **R-Cache TTL cleanup is operationally critical.** Monitored, alerted.
- **Adaptive windows can oscillate.** EMA + bounds + min-samples + damping mitigates.
- **Learned-keywords audit UI adds ongoing UX maintenance.** Users will delete things and Alfred has to honor that. Worth it for trust.

---

## 10. Open questions

1. **Confidence threshold for `review` flag.** Suggested 0.6; needs prototype data.
2. **Embedding model choice for R3b.** Likely OpenAI `text-embedding-3-small` or equivalent.
3. **`ChannelSourceRule` migration edge cases.** Catch during dry-run.
4. **Critical-flag concept for R-AwayMode Option 3.** Deferred.
5. **Bot focus-mode failure mode.** Investigation prerequisite.
6. **Two product modes UX surfacing.** Phase 2 design.
7. **Reset weighting for "things have changed."** Suggested 50%.
8. **Walkback time cap of 2 hours.** Tune from production data.
9. **R-Cache size estimation.** Model storage cost before launch.
10. **[v3.2] R-Transparency UX scope.** Specifics of audit UI layout, "are you sure" confirmations on bulk-delete, etc. Phase 2 design.

---

## 11. Deferred from review

- **R-AwayMode Option 3** ("push only if critical").
- **Embedding-based topic affinity** (R3d Phase 4 upgrade).
- **PTO catch-up feature.**
- **LLM-based short-ack classifier** (replacing extended `substance_filter`).
- **Cross-channel deduplication.**
- **Team-level classification or shared rule sets.**
- **Mobile-vs-desktop differential behavior.**
- **[v3.2] GDPR-style bulk-export** of derived data (audit UI is in scope; full export is not).

---

## 12. What's explicitly NOT in this spec

- Cross-app triage.
- Cross-channel deduplication.
- Full PTO catch-up workflow.
- Calendar-driven away mode auto-detection.
- Embedding-based topic centroids.
- Mobile-vs-desktop differential behavior.
- Team-level classification or shared rule sets.
- Incident-mode high-volume handling.

---

*End of PRD v3.2.*
