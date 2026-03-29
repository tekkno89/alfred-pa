# Todo System

## Overview

Full-featured task management with priority levels, due dates, recurring tasks (RFC 5545 RRULE), scheduled reminders via APScheduler, and Slack DM notifications with interactive buttons.

## Todo Lifecycle

```mermaid
stateDiagram-v2
    [*] --> Open: create
    Open --> Open: update / snooze
    Open --> Completed: complete
    Completed --> [*]
    Open --> [*]: delete

    state Open {
        [*] --> NoDueDate
        [*] --> Scheduled
        Scheduled --> Overdue: past due_at
        Scheduled --> ReminderSent: APScheduler fires
        ReminderSent --> Overdue: past due_at
    }

    Completed --> Open: recurrence_rule set\ncreate next occurrence
```

## Architecture

```mermaid
flowchart TD
    subgraph "Entry Points"
        TOOL[manage_todos Tool<br/>LLM agent action]
        API[REST API<br/>/todos endpoints]
        SLACK_BTN[Slack Buttons<br/>Mark Done / Snooze]
    end

    subgraph "Backend"
        REPO[TodoRepository<br/>CRUD + filtering]
        REC[RecurrenceService<br/>RFC 5545 RRULE]
        SCHED[APScheduler<br/>reminder jobs]
        NOTIFY[TodoNotificationService<br/>Slack DM + SSE]
    end

    subgraph "Delivery"
        SLACK_DM[Slack DM<br/>with buttons]
        SSE[SSE Event<br/>todo_due]
        WEBHOOK[Webhooks]
    end

    TOOL --> REPO
    API --> REPO
    SLACK_BTN --> REPO

    REPO -->|on create/update| SCHED
    SCHED -->|at due_at| NOTIFY
    NOTIFY --> SLACK_DM
    NOTIFY --> SSE
    NOTIFY --> WEBHOOK

    REPO -->|on complete| REC
    REC -->|has rule| REPO
    REC -->|schedule next| SCHED
```

## Reminder Flow

```mermaid
sequenceDiagram
    participant Sched as APScheduler
    participant Notify as TodoNotificationService
    participant DB as PostgreSQL
    participant Slack as Slack API
    participant SSE as SSE Stream

    Sched->>Notify: send_due_reminder(todo_id, user_id)
    Notify->>DB: Fetch todo + user
    alt Todo already completed
        Notify-->>Sched: Skip
    else Todo open
        Notify->>Slack: Post DM with buttons
        Note over Slack: Mark Done | Snooze 5m | 15m | 1h
        Notify->>SSE: Publish todo_due event
        Notify->>DB: Update reminder_sent_at
    end

    Note over Slack: User clicks Snooze 15m
    Slack->>DB: Update due_at += 15min
    Slack->>Sched: Schedule new reminder
    Slack->>Slack: Reply in thread "Snoozed"

    Note over Slack: User clicks Mark Done
    Slack->>DB: Set status=completed
    alt Has recurrence_rule
        DB->>DB: Create next occurrence
        DB->>Sched: Schedule reminder for next
    end
    Slack->>Slack: Reply in thread "Completed"
```

## Recurrence

Uses RFC 5545 RRULE format via `dateutil.rrule`:

| RRULE Example | Meaning |
|---------------|---------|
| `FREQ=DAILY;INTERVAL=1` | Every day |
| `FREQ=WEEKLY;BYDAY=MO,WE,FR` | Mon, Wed, Fri |
| `FREQ=MONTHLY;BYMONTHDAY=1` | First of each month |
| `FREQ=WEEKLY;INTERVAL=2` | Every 2 weeks |

On completion of a recurring todo:
1. `RecurrenceService.create_next_occurrence()` computes next due date
2. New todo created with same title/priority/tags, linked via `recurrence_parent_id`
3. Reminder scheduled for the new todo

## Priority Levels

| Value | Label | Color |
|-------|-------|-------|
| 0 | Urgent (P0) | Red |
| 1 | High (P1) | Orange |
| 2 | Medium (P2) | Blue |
| 3 | Low (P3) | Gray |

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/todos` | List todos with filters (status, priority, starred, due date) + pagination |
| POST | `/todos` | Create todo |
| PATCH | `/todos/{id}` | Update todo |
| POST | `/todos/{id}/complete` | Mark complete (triggers recurrence) |
| DELETE | `/todos/{id}` | Delete todo |

## Key Files

| File | Purpose |
|------|---------|
| `backend/app/tools/todos.py` | `ManageTodosTool` — agent tool |
| `backend/app/api/todos.py` | REST API endpoints |
| `backend/app/db/models/todo.py` | SQLAlchemy model |
| `backend/app/db/repositories/todo.py` | Data access layer |
| `backend/app/schemas/todo.py` | Pydantic request/response schemas |
| `backend/app/services/todo_notifications.py` | Reminder delivery (Slack DM + SSE) |
| `backend/app/services/recurrence.py` | RFC 5545 RRULE parsing + next occurrence |
| `frontend/src/pages/TodosPage.tsx` | Todo list with filters and create/edit dialog |
| `frontend/src/hooks/useTodos.ts` | React Query hooks |
| `frontend/src/components/dashboard/TodosCard.tsx` | Dashboard widget |

## Status

✅ Complete
