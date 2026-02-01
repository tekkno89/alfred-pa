# Phase 2: Agent & Chat API

**Status:** ✅ Complete

---

## Goal

Implement the LangGraph Alfred agent and chat API endpoints so the backend can be tested via HTTP requests (curl, Swagger UI) without needing the webapp.

---

## Tasks

### API Schemas
- [x] Create session schemas (SessionCreate, SessionResponse, SessionList)
- [x] Create message schemas (MessageCreate, MessageResponse, MessageList)
- [x] Create streaming response schema

### API Dependencies
- [x] Create database dependency (get_db)
- [x] Create simplified auth dependency (skip auth or API key for testing)

### Session Endpoints
- [x] POST /api/sessions - Create new session
- [x] GET /api/sessions - List sessions (paginated)
- [x] GET /api/sessions/{id} - Get session with messages
- [x] DELETE /api/sessions/{id} - Delete session

### Message/Chat Endpoints
- [x] POST /api/sessions/{id}/messages - Send message, get streaming response
- [x] GET /api/sessions/{id}/messages - Get message history (paginated)

### Repositories
- [x] Create SessionRepository with CRUD operations
- [x] Create MessageRepository with CRUD operations

### LLM Provider
- [x] Create LLM provider abstraction interface
- [x] Implement Vertex AI Gemini provider
- [x] Implement Vertex AI Claude provider
- [x] Implement OpenRouter provider (multi-model access)
- [x] Add provider selection via config/model name prefix

### LangGraph Agent
- [x] Define AgentState TypedDict
- [x] Create process_message node (prepares user input)
- [x] Create retrieve_context node (gets recent messages + memories)
- [x] Create generate_response node (calls LLM)
- [x] Create extract_memories node (extracts facts to remember)
- [x] Create save_message node (persists to database)
- [x] Build the agent graph with edges
- [x] Add streaming support

### Testing
- [x] Write session endpoint integration tests
- [x] Write message endpoint integration tests
- [x] Write agent node unit tests
- [x] Test streaming responses work correctly

---

## API Specification

### Sessions

```
POST /api/sessions
Request:  { "title": "optional title" }
Response: { "id": "uuid", "title": "...", "source": "webapp", "created_at": "..." }

GET /api/sessions
Response: { "items": [...], "total": 10, "page": 1, "size": 20 }

GET /api/sessions/{id}
Response: { "id": "...", "title": "...", "messages": [...], ... }

DELETE /api/sessions/{id}
Response: { "success": true }
```

### Messages

```
POST /api/sessions/{id}/messages
Request:  { "content": "Hello Alfred!" }
Response: Server-Sent Events stream
  data: {"type": "token", "content": "Hello"}
  data: {"type": "token", "content": "!"}
  data: {"type": "done", "message_id": "uuid"}

GET /api/sessions/{id}/messages
Response: { "items": [...], "total": 5 }
```

---

## Agent Graph

```
                    ┌─────────────────┐
                    │      START      │
                    └────────┬────────┘
                             │
                             ▼
                    ┌─────────────────┐
                    │ process_message │
                    │                 │
                    │ - Validate input│
                    │ - Create state  │
                    └────────┬────────┘
                             │
                             ▼
                    ┌─────────────────┐
                    │retrieve_context │
                    │                 │
                    │ - Last N msgs   │
                    │ - Query memories│
                    └────────┬────────┘
                             │
                             ▼
                    ┌─────────────────┐
                    │generate_response│
                    │                 │
                    │ - Build prompt  │
                    │ - Call LLM      │
                    │ - Stream tokens │
                    └────────┬────────┘
                             │
                             ▼
                    ┌─────────────────┐
                    │extract_memories │
                    │                 │
                    │ - Find facts    │
                    │ - Store prefs   │
                    └────────┬────────┘
                             │
                             ▼
                    ┌─────────────────┐
                    │  save_message   │
                    │                 │
                    │ - Persist msgs  │
                    │ - Update session│
                    └────────┬────────┘
                             │
                             ▼
                    ┌─────────────────┐
                    │       END       │
                    └─────────────────┘
```

---

## Files to Create

```
backend/app/
├── api/
│   ├── __init__.py          # UPDATE: Include new routers
│   ├── deps.py              # NEW: Dependencies
│   └── sessions.py          # NEW: Session & message endpoints
├── schemas/
│   ├── __init__.py          # UPDATE: Export schemas
│   ├── session.py           # NEW: Session schemas
│   └── message.py           # NEW: Message schemas
├── agents/
│   ├── __init__.py          # UPDATE: Export agent
│   ├── alfred.py            # NEW: Alfred agent graph
│   ├── state.py             # NEW: Agent state definition
│   └── nodes.py             # NEW: Node implementations
├── core/
│   ├── __init__.py
│   └── llm.py               # NEW: LLM provider abstraction
└── db/
    └── repositories/
        ├── __init__.py      # UPDATE: Export repositories
        ├── base.py          # NEW: Base repository class
        ├── session.py       # NEW: Session repository
        └── message.py       # NEW: Message repository

backend/tests/
├── test_sessions.py         # NEW: Session endpoint tests
├── test_messages.py         # NEW: Message endpoint tests
└── test_agent.py            # NEW: Agent unit tests
```

---

## Verification

1. Start services: `docker-compose -f docker-compose.dev.yml up`
2. Run migrations: `docker-compose exec backend alembic upgrade head`
3. Open Swagger UI: http://localhost:8000/docs
4. Create a session: POST /api/sessions
5. Send a message: POST /api/sessions/{id}/messages with `{"content": "Hello!"}`
6. Verify streaming response in terminal or via curl:
   ```bash
   curl -N -X POST http://localhost:8000/api/sessions/{id}/messages \
     -H "Content-Type: application/json" \
     -d '{"content": "Hello Alfred!"}'
   ```
7. Check message history: GET /api/sessions/{id}/messages
8. Run tests: `docker-compose exec backend pytest tests/test_sessions.py tests/test_messages.py`
