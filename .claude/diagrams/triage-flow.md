# Triage System Flow

## Overview

The triage system classifies incoming Slack messages during focus sessions using LLM-powered analysis. Messages are routed through a pipeline of enrichment, classification, and delivery stages. Raw message text is never persisted — only abstracts and metadata are stored.

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
    PIPE --> ENR[Enrich]
    ENR --> CLS[Classify]
    CLS --> STORE[Store classification<br/>no raw text]
    STORE --> URG{Urgency?}
    URG -->|urgent| NOTIFY[Slack DM + SSE<br/>triage.urgent]
    URG -->|digest| HOLD[Hold for break/end]
    URG -->|noise| FILED[Filed, hidden<br/>during session]
    URG -->|review| SHOW[Show in Needs<br/>Attention filter]
```

## Classification Decision Flow

```mermaid
flowchart TD
    MSG[Incoming Message] --> PATH{Classification<br/>path?}
    PATH -->|DM| VIP{Sender is VIP?}
    PATH -->|Channel| KW{Keyword rule<br/>match?}
    VIP -->|Yes| U1[Return urgent<br/>confidence: 1.0]
    VIP -->|No| LLM[LLM Classification]
    KW -->|Match| OV[Return rule's<br/>urgency_override]
    KW -->|No match| PRI{Channel priority<br/>= critical?}
    PRI -->|Yes| U2[Return urgent<br/>confidence: 0.9]
    PRI -->|No| LLM
    LLM --> PARSE[Parse JSON response]
    PARSE --> RES[urgency + confidence<br/>+ reason + abstract]
    PARSE -->|Error| FALLBACK[Default to review<br/>confidence: 0.3]

    style LLM fill:#e8f4fd,stroke:#0284c7
    style FALLBACK fill:#fef3c7,stroke:#d97706
```

## Urgency Levels

| Level | DB Value | Display Label | Delivery | Description |
|-------|----------|---------------|----------|-------------|
| Urgent | `urgent` | Urgent | Immediate Slack DM + SSE | Production incidents, VIP senders, explicit urgency |
| Digest | `digest` | Digest Messages | Held for break/end | Noteworthy work messages, questions, project updates |
| Noise | `noise` | Noise | Silent | Memes, casual chatter, automated notifications |
| Unclassified | `review` | Unclassified | Shown in Needs Attention | LLM uncertain, flagged for manual review |
| Session Digest | `digest_summary` | Session Digest | At break/end | Consolidated summary of digest items |

**API pseudo-filters:**
- `needs_attention` (alias: `reviewable`) → resolves to `["urgent", "review", "digest_summary"]`
- `digest` → shows all digest items including those consolidated into summaries

## Digest Consolidation Flow

```mermaid
sequenceDiagram
    participant M as Incoming Messages
    participant DB as PostgreSQL
    participant DS as TriageDeliveryService
    participant S as Slack DM
    participant SSE as SSE Stream

    Note over M,DB: During focus session
    M->>DB: Store as digest<br/>surfaced_at_break=false<br/>digest_summary_id=NULL

    Note over DS: At pomodoro break or focus end
    DS->>DB: Query unsurfaced digest items
    DB-->>DS: N digest items
    DS->>DB: Create digest_summary row<br/>urgency=digest_summary<br/>child_count=N
    DS->>DB: Link children via<br/>digest_summary_id FK
    DS->>S: Send digest DM
    DS->>SSE: Publish triage.break_check_slack
```

### Consolidated Item Visibility

- **Default queries**: Items with `digest_summary_id IS NOT NULL` are hidden (replaced by their summary)
- **Digest Messages filter**: Skips the consolidation filter, showing all individual digest items including consolidated ones — enables feedback on each item
- **Digest children endpoint**: `GET /classifications/{id}/digest-children` returns items linked to a summary

## Enrichment Context

```mermaid
flowchart LR
    subgraph Sources
        SETTINGS[User Settings<br/>sensitivity, rules]
        VIP[VIP List]
        FOCUS[Active Focus<br/>Session]
        CHAN[Channel Config<br/>priority, keywords]
        SLACK[Slack API<br/>names, permalink]
    end
    subgraph Payload
        EP[EnrichedTriagePayload<br/>- user context<br/>- channel context<br/>- display names<br/>- classification guidance]
    end
    Sources --> EP
    EP --> LLM[LLM Classifier]
```

## Real-Time Notifications

| SSE Event | Trigger | Payload |
|-----------|---------|---------|
| `triage.urgent` | Urgent classification | classification_id, sender, channel, abstract, permalink |
| `triage.break_check_slack` | Focus break with digest items | count, session_id |
| `triage.break_notification_clear` | Digest reviewed | session_id |
| `triage.debug` | Debug mode enabled | Classification details (no raw text) |

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/triage/settings` | Get user triage settings |
| PATCH | `/triage/settings` | Update settings (sensitivity, always-on, debug) |
| GET | `/triage/channels` | List monitored channels |
| POST | `/triage/channels` | Add monitored channel |
| PATCH | `/triage/channels/{id}` | Update channel config |
| DELETE | `/triage/channels/{id}` | Remove channel |
| GET | `/triage/channels/{id}/rules` | List keyword rules |
| POST | `/triage/channels/{id}/rules` | Add keyword rule |
| PATCH | `/triage/channels/{id}/rules/{rule_id}` | Update rule |
| DELETE | `/triage/channels/{id}/rules/{rule_id}` | Remove rule |
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
| GET | `/triage/analytics/session-stats` | Counts by urgency level |

## Key Files

| File | Purpose |
|------|---------|
| `backend/app/api/triage.py` | REST API endpoints |
| `backend/app/api/slack.py` | Slack event handler (triggers triage) |
| `backend/app/services/triage_router.py` | Routes events to pipeline |
| `backend/app/services/triage_enrichment.py` | Gathers classification context |
| `backend/app/services/triage_classifier.py` | LLM classification logic |
| `backend/app/services/triage_pipeline.py` | Orchestration + urgent delivery |
| `backend/app/services/triage_delivery.py` | Digest consolidation + break notifications |
| `backend/app/services/triage_cache.py` | Redis channel set for O(1) lookup |
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
