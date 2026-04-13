# Triage System Flow

## Overview

The triage system classifies incoming Slack messages using LLM-powered analysis into P0-P3 priority levels. It operates during focus sessions or in always-on mode (with configurable alert toggles per priority level). Messages are routed through a pipeline of enrichment, classification, and delivery stages. Raw message text is never persisted — only abstracts and metadata are stored.

## Message Classification Pipeline

```mermaid
flowchart TD
    SE[Slack Event] --> ED{Event Dedup<br/>Redis 5min TTL}
    ED -->|Duplicate| SKIP[Return 200, skip]
    ED -->|New| MD{Message Dedup<br/>channel:ts}
    MD -->|Duplicate| SKIP
    MD -->|New| FM[Focus Mode Checks<br/>Auto-replies & VIP bypass]
    FM --> TR[TriageEventRouter.route_event]
    TR --> DM{Is DM?}
    DM -->|Yes| AUTH[Check recipient<br/>authorizations]
    DM -->|No| MON{is_monitored_channel?<br/>Redis SET O1}
    AUTH --> TRIAGE_EN{User has<br/>triage enabled?}
    MON -->|No| DONE[Skip]
    MON -->|Yes| USERS[Get users monitoring<br/>this channel]
    USERS --> TRIAGE_EN
    TRIAGE_EN -->|No| DONE
    TRIAGE_EN -->|Yes| JOB[Enqueue ARQ job<br/>triage queue]
    JOB --> PIPE[TriagePipeline.process]
    PIPE --> ENR[Enrich with context]
    ENR --> CLS[Classify with LLM]
    CLS --> STORE[Store classification<br/>no raw text]
    STORE --> FILT{Alerts enabled<br/>for priority?}
    FILT -->|Disabled| QUEUE[Queue for digest]
    FILT -->|Enabled| DEDUP{Dedup<br/>window?}
    DEDUP -->|Recent alert| QUEUE
    DEDUP -->|New| PRI{Priority?}
    PRI -->|P0| NOTIFY[Immediate Slack DM + SSE]
    PRI -->|P1| DIGEST1[Queue for P1 digest<br/>configurable cadence]
    PRI -->|P2| DIGEST2[Queue for P2 digest<br/>configurable cadence]
    PRI -->|P3| DIGEST3[Queue for P3 digest<br/>daily summary]
    PRI -->|review| SHOW[Show in Needs<br/>Attention filter]
```

## Classification Decision Flow

```mermaid
flowchart TD
    MSG[Incoming Message] --> PATH{Classification<br/>path?}
    PATH -->|DM| VIP{Sender is VIP?}
    PATH -->|Channel| INST{Channel has<br/>triage instructions?}
    VIP -->|Yes| U1[Return P0<br/>confidence: 1.0]
    VIP -->|No| CUST{User has custom<br/>priority definitions?}
    INST -->|Yes| GUIDE[Apply instructions<br/>+ user rules]
    INST -->|No| CPRI{Channel priority<br/>= critical?}
    CPRI -->|Yes| U2[Return P0<br/>confidence: 0.9]
    CPRI -->|No| CUST
    GUIDE --> LLM
    CUST -->|Yes| LLM[LLM Classification<br/>with custom definitions]
    CUST -->|No| LLM2[LLM Classification<br/>with defaults]
    LLM --> PARSE[Parse JSON response]
    LLM2 --> PARSE
    PARSE --> RES[priority + confidence<br/>+ reason + abstract]
    PARSE -->|Error| FALLBACK[Return review<br/>confidence: 0.3]

    style LLM fill:#e8f4fd,stroke:#0284c7
    style LLM2 fill:#e8f4fd,stroke:#0284c7
    style FALLBACK fill:#fef3c7,stroke:#d97706
```

## Priority Levels

| Level | DB Value | Display Label | Delivery | Description |
|-------|----------|---------------|----------|-------------|
| P0 | `p0` | Urgent | Immediate Slack DM + SSE | Production incidents, VIP senders, explicit urgency |
| P1 | `p1` | High | Scheduled digest (configurable) | Time-sensitive, direct asks, important questions, deadlines |
| P2 | `p2` | Medium | Scheduled digest (configurable) | Noteworthy but not time-sensitive, updates, FYI, discussions |
| P3 | `p3` | Low | Daily summary | General chatter, memes, social messages, automated notifications |
| Review | `review` | Unclassified | Shown in Needs Attention | LLM uncertain, flagged for manual review |
| Session Digest | `digest_summary` | Session Digest | At break/end | Consolidated summary of P1/P2 items |

**User-customizable priority definitions:** Users can define custom P0-P3 definitions via the Triage Wizard or manual settings. These definitions guide the LLM classifier for personalized results.

**Always-on mode:** When `is_always_on` is enabled, triage runs even outside focus sessions. Each priority level has its own alert toggle (`p0_alerts_enabled`, `p1_alerts_enabled`, etc.) for fine-grained control.

**API pseudo-filters:**
- `needs_attention` (alias: `reviewable`) → resolves to `["p0", "review", "digest_summary"]`
- `digest` → shows all P1/P2 items including those consolidated into summaries

## Digest Cadence Configuration

Users can configure when they receive digest notifications for each priority level:

```mermaid
flowchart LR
    subgraph P1 Config
        P1INT[Interval: e.g. 60 min]
        P1HRS[Active hours: 9am-6pm]
        P1TIME[Specific times: 9am, 12pm, 5pm]
        P1OUT[Outside hours: queue or notify]
    end
    subgraph P2 Config
        P2INT[Interval: e.g. 120 min]
        P2HRS[Active hours]
        P2TIME[Specific times]
    end
    subgraph P3 Config
        P3TIME[Daily summary time: 5pm]
    end
```

**Configuration fields:**
- `p1_digest_interval_minutes`, `p2_digest_interval_minutes` — how often to deliver digests
- `p1_digest_active_hours_start/end`, `p2_digest_active_hours_start/end` — only deliver during these hours
- `p1_digest_times`, `p2_digest_times` — specific times for digest delivery
- `p1_digest_outside_hours_behavior`, `p2_digest_outside_hours_behavior` — "queue" or "notify"
- `p3_digest_time` — time for daily P3 summary

## Alert Deduplication

To prevent notification spam from rapid messages in the same channel/thread:

```mermaid
sequenceDiagram
    participant M as Message 1
    participant M2 as Message 2
    participant DB as Classification
    participant ALERT as Alert System
    participant USER as User

    M->>DB: Store classification<br/>last_alerted_at = now
    M->>ALERT: Send immediate alert
    ALERT->>USER: Slack DM + SSE

    Note over M2: 5 minutes later<br/>same channel/thread

    M2->>DB: Store classification
    M2->>ALERT: Check last_alerted_at
    ALT Within dedup window (default 30 min)
        ALERT->>DB: Update, no new alert
        ALERT->>USER: Silent - queued for digest
    ELSE Outside dedup window
        ALERT->>USER: New alert sent
    END
```

## Enrichment Context

```mermaid
flowchart LR
    subgraph Sources
        SETTINGS[User Settings<br/>sensitivity, custom rules]
        PRIOR[Custom Priority<br/>Definitions P0-P3]
        VIP[VIP List]
        FOCUS[Active Focus<br/>Session]
        CHAN[Channel Config<br/>priority, instructions]
        SLACK[Slack API<br/>names, permalink]
        THREAD[Thread Context<br/>summarized messages]
        DMCTX[DM Context<br/>recent conversation]
    end
    subgraph Payload
        EP[EnrichedTriagePayload<br/>- user context<br/>- channel context<br/>- conversation context<br/>- classification guidance]
    end
    Sources --> EP
    EP --> LLM[LLM Classifier]
```

**Key enrichment fields:**
- `channel_triage_instructions` — per-channel custom instructions for classification
- `custom_classification_rules` — user-defined classification guidance
- `p0_definition` through `p3_definition` — user-customizable priority definitions
- `thread_context_summary` — summarized recent thread messages (for channel messages)
- `dm_conversation_context` — summarized recent DM messages (for DMs)

## Digest Consolidation Flow

```mermaid
sequenceDiagram
    participant M as Incoming Messages
    participant DB as PostgreSQL
    participant DS as TriageDeliveryService
    participant S as Slack DM
    participant SSE as SSE Stream

    Note over M,DB: During focus session or always-on
    M->>DB: Store with priority<br/>queued_for_digest=true

    Note over DS: At scheduled digest time<br/>or pomodoro break
    DS->>DB: Query queued items for priority
    DB-->>DS: N digest items
    DS->>DB: Create digest_summary row<br/>priority=digest_summary<br/>child_count=N
    DS->>DB: Link children via<br/>digest_summary_id FK
    DS->>S: Send digest DM
    DS->>SSE: Publish triage.break_check_slack
```

### Consolidated Item Visibility

- **Default queries**: Items with `digest_summary_id IS NOT NULL` are hidden (replaced by their summary)
- **Digest Messages filter**: Skips the consolidation filter, showing all individual digest items including consolidated ones — enables feedback on each item
- **Digest children endpoint**: `GET /classifications/{id}/digest-children` returns items linked to a summary

## Priority Calibration

Users can calibrate the priority system by rating sample Slack messages:

```mermaid
flowchart TD
    START[User opens calibration] --> SAMPLE[TriageCalibrationService<br/>samples 10 messages]
    SAMPLE --> CATEG[Categorize by channel type<br/>DM, public, private]
    CATEG --> DISPLAY[Display each message<br/>for user rating]
    DISPLAY --> RATE[User rates P0-P3]
    RATE --> COVERAGE{All priorities<br/>covered?}
    COVERAGE -->|No| DISPLAY
    COVERAGE -->|Yes| FEEDBACK[Show calibration<br/>confidence score]
```

**Calibration fields in feedback:**
- `was_correct` — whether the user agrees with the classification
- `correct_priority` — what the user thinks it should have been
- `feedback_text` — optional explanation

## Real-Time Notifications

| SSE Event | Trigger | Payload |
|-----------|---------|---------|
| `triage.urgent` | P0 classification | classification_id, sender, channel, abstract, permalink |
| `triage.break_check_slack` | Focus break with digest items | count, session_id |
| `triage.break_notification_clear` | Digest reviewed | session_id |
| `triage.debug` | Debug mode enabled | Classification details (no raw text) |

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/triage/settings` | Get user triage settings |
| PATCH | `/triage/settings` | Update settings (sensitivity, alerts, digest config, custom definitions) |
| GET | `/triage/channels` | List monitored channels |
| POST | `/triage/channels` | Add monitored channel |
| PATCH | `/triage/channels/{id}` | Update channel config (priority, instructions, active) |
| DELETE | `/triage/channels/{id}` | Remove channel |
| GET | `/triage/channels/{id}/exclusions` | List source exclusions |
| POST | `/triage/channels/{id}/exclusions` | Add exclusion |
| DELETE | `/triage/channels/{id}/exclusions/{id}` | Remove exclusion |
| GET | `/triage/slack-channels` | List available Slack channels |
| GET | `/triage/classifications` | List with filters + pagination |
| PATCH | `/triage/classifications/reviewed` | Bulk mark reviewed/unreviewed |
| GET | `/triage/classifications/{id}/digest-children` | Get digest summary children |
| GET | `/triage/digest/{session_id}` | Get session digest |
| GET | `/triage/digest/latest` | Get latest 50 as digest |
| POST | `/triage/analytics/feedback` | Submit classification feedback |
| GET | `/triage/analytics/session-stats` | Counts by priority level |
| POST | `/triage/wizard/definitions` | AI-generated custom priority definitions |
| POST | `/triage/calibration/sample` | Sample messages for calibration |
| POST | `/triage/calibration/generate` | Generate definitions from ratings |

## Key Files

| File | Purpose |
|------|---------|
| `backend/app/api/triage.py` | REST API endpoints |
| `backend/app/api/slack.py` | Slack event handler (triggers triage) |
| `backend/app/services/triage_router.py` | Routes events to pipeline |
| `backend/app/services/triage_enrichment.py` | Gathers classification context |
| `backend/app/services/triage_classifier.py` | LLM classification logic |
| `backend/app/services/triage_pipeline.py` | Orchestration + urgent delivery |
| `backend/app/services/triage_delivery.py` | Digest consolidation + scheduled delivery |
| `backend/app/services/triage_cache.py` | Redis channel set for O(1) lookup |
| `backend/app/services/triage_wizard.py` | AI-generated priority definitions |
| `backend/app/services/triage_calibration.py` | Sample messages for calibration |
| `backend/app/db/models/triage.py` | Database models |
| `backend/app/db/repositories/triage.py` | Data access layer |
| `backend/app/schemas/triage.py` | Request/response schemas |
| `frontend/src/hooks/useTriage.ts` | React Query hooks |
| `frontend/src/pages/TriagePage.tsx` | Classification list + filters |
| `frontend/src/pages/TriageSettingsPage.tsx` | Triage configuration UI |
| `frontend/src/components/dashboard/TriageCard.tsx` | Dashboard widget |
| `frontend/src/components/triage/ClassificationDetailModal.tsx` | Detail view + feedback UI |

## Status

✅ Complete
