# Slack Integration Flow

## Account Linking Flow

```mermaid
sequenceDiagram
    participant U as User
    participant S as Slack
    participant B as Backend
    participant R as Redis
    participant W as Webapp

    U->>S: /alfred-link
    S->>B: POST /api/slack/commands
    B->>R: Store code (TTL 10min)
    B->>S: Return code to user
    S->>U: Display code (ephemeral)
    U->>W: Enter code in Settings
    W->>B: POST /api/auth/link-slack
    B->>R: Validate & consume code
    B->>B: Update user.slack_user_id
    B->>W: Return success
    W->>U: Show "Linked" status
```

## Message Flow (Slack → Webapp)

```mermaid
sequenceDiagram
    participant U as User
    participant S as Slack
    participant B as Backend
    participant R as Redis
    participant A as AlfredAgent
    participant DB as PostgreSQL

    U->>S: Send message in DM/thread
    S->>B: POST /api/slack/events
    B->>R: Check event deduplication
    alt Duplicate event
        B->>S: Return 200 OK (skip)
    else New event
        B->>R: Mark event as processed
        B->>S: Return 200 OK immediately
        B->>B: Background task starts
        B->>DB: Find/create session by thread
        B->>A: Process message
        A->>A: Generate response
        B->>DB: Save messages
        B->>S: Post response to thread
    end
```

## Cross-Sync Flow (Webapp → Slack)

```mermaid
sequenceDiagram
    participant U as User
    participant W as Webapp
    participant B as Backend
    participant A as AlfredAgent
    participant S as Slack

    U->>W: Send message in Slack-originated session
    W->>B: POST /api/sessions/{id}/messages
    B->>B: Check session has Slack metadata
    B->>S: Post user message (with attribution)
    B->>A: Process message (streaming)
    A-->>W: Stream tokens
    A->>A: Complete response
    B->>S: Post AI response to thread
    B-->>W: Stream complete
```

## Components

### Backend Endpoints
- `POST /api/slack/events` - Slack Events API webhook
- `POST /api/slack/commands` - Slash command handler
- `GET /api/auth/slack-status` - Check linking status
- `POST /api/auth/link-slack` - Link account with code
- `POST /api/auth/unlink-slack` - Unlink account

### Services
- **SlackService** - Signature verification, send messages, get user info
- **LinkingService** - Generate/validate linking codes in Redis

### Event Deduplication
- Redis key: `slack_event:{event_id}`
- TTL: 5 minutes
- Prevents duplicate processing when Slack retries

### Cross-Sync Attribution
User messages from webapp appear in Slack as:
```
:speech_balloon: username (via webapp):
> message content here
```
