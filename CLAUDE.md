# Alfred AI Assistant - Claude Code Instructions

## Project Overview

Alfred is a personal AI assistant built with LangGraph, FastAPI, React, and Slack integration. See `.claude/plans/` for the current implementation plan and task tracking.

## Quick Reference

- **Backend:** `backend/` - FastAPI + LangGraph (Python 3.11+)
- **Frontend:** `frontend/` - React + Tailwind + shadcn/ui
- **Database:** PostgreSQL 16 + pgvector, Redis 7
- **LLM:** Vertex AI (Gemini + Claude, configurable), OpenRouter
- **Tools:** Web search (Tavily) with ReAct loop
- **Package Manager:** UV (Python), npm (Frontend)

## Development Commands

### Start Development Environment
```bash
docker-compose -f docker-compose.dev.yml up
```

### Backend (UV Package Manager)
```bash
cd backend

# Install UV (if not already installed)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Install dependencies
uv sync                         # Install all deps (including dev)
uv sync --no-dev                # Install production deps only

# Add/remove dependencies
uv add <package>                # Add a dependency
uv add --dev <package>          # Add a dev dependency
uv remove <package>             # Remove a dependency

# Run commands in the virtual environment
uv run ruff check .             # Run linter
uv run mypy app                 # Run type checker

# Database
uv run alembic upgrade head            # Run all migrations
uv run alembic revision --autogenerate -m "description"  # Create migration
uv run alembic downgrade -1            # Rollback one version
uv run python -m app.db.seed           # Seed dev database
```

### Backend (Docker - recommended for development)
```bash
# All backend commands run in Docker for consistency
docker-compose -f docker-compose.dev.yml exec backend pytest
docker-compose -f docker-compose.dev.yml exec backend alembic upgrade head
```

### Running Tests

**IMPORTANT: Before running tests, determine whether the dev environment is running inside Docker or locally.** Check by running `docker-compose -f docker-compose.dev.yml ps` — if the `backend` container is running, use the Docker commands. If not (or if you're developing outside Docker), use the local commands with the required env vars.

The app requires `JWT_SECRET` to be set even for unit tests (the conftest imports the app which triggers settings validation). The test database defaults to hostname `postgres` (Docker), so set `TEST_DB_HOST=localhost` when running outside Docker.

**Inside Docker (recommended — runs all tests including integration):**
```bash
docker-compose -f docker-compose.dev.yml exec backend pytest
docker-compose -f docker-compose.dev.yml exec backend pytest tests/test_tools.py -v  # specific file
```

**Outside Docker (unit tests only — no Postgres/Redis required):**
```bash
cd backend
JWT_SECRET=test-secret DATABASE_URL=postgresql+asyncpg://alfred:alfred@localhost:5432/alfred uv run pytest tests/test_tools.py tests/test_agent.py tests/test_focus_orchestrator.py tests/services/ tests/api/test_slack.py -v
```

**Outside Docker (full suite — requires Docker stack running for Postgres):**
```bash
cd backend
JWT_SECRET=test-secret DATABASE_URL=postgresql+asyncpg://alfred:alfred@localhost:5432/alfred TEST_DB_HOST=localhost uv run pytest
```

**Test categories:**
- **Unit tests** (no DB): `tests/test_tools.py`, `tests/test_agent.py`, `tests/test_focus_orchestrator.py`, `tests/services/`, `tests/api/test_slack.py`
- **Integration tests** (need Postgres): `tests/integration/`, other `tests/api/` files

### Frontend
```bash
cd frontend
npm install
npm run dev                     # Start dev server
npm test                        # Run tests
npm run build                   # Production build
```

## Task Tracking

Implementation tasks are tracked in `.claude/plans/`.

### Plan Files Structure
- **00-project-overview.md** - Master overview with phase status and architecture
- **01-infrastructure.md** - Phase 1: Monorepo, Docker, database setup (✅ Complete)
- **02-agent-chat-api.md** - Phase 2: LangGraph agent, chat endpoints (✅ Complete)
- **03-authentication.md** - Phase 3: Email/password auth, JWT (✅ Complete)
- Additional phase files created as needed

### CRITICAL: Task File Creation (Session Crash Protection)

**BEFORE starting any implementation work, you MUST:**

1. **Create or update the task file** for the phase you're working on in `.claude/plans/`
2. The task file should include:
   - Goal/objective of the phase
   - Scope (in/out of scope)
   - Detailed task checklist with `[ ]` markers
   - API specifications (if applicable)
   - Files to create/modify
   - Verification steps
3. **Update the task file incrementally** as you complete work:
   - Mark tasks `[x]` immediately when completed (don't wait until end)
   - Add notes about implementation decisions
   - Document any issues encountered and how they were resolved
   - Add test results when tests pass
4. This ensures work can be resumed if the session crashes

### Workflow
1. Start each session by reading `00-project-overview.md` to understand current status
2. **Create/update the task file BEFORE writing any code**
3. Read the relevant phase file for detailed tasks
4. Mark tasks `[x]` immediately when complete (not at the end)
5. Update phase status in overview when phase completes
6. Add new tasks as they emerge

## Documentation & Diagrams

### Diagram Generation

Store architecture and flow diagrams in `.claude/diagrams/` using Mermaid format.

**When to create diagrams:**
- New API flows or endpoints
- Authentication/authorization flows
- Database schema changes (ERD updates)
- Agent/LLM interaction flows
- System architecture changes
- Complex business logic flows

**Diagram file format:**
````markdown
# Title

## Description

```mermaid
graph TD
    A[Component] --> B[Component]
```

## Components
- Component descriptions
````

### Existing Diagrams
- `architecture.md` - System overview
- `agent-flow.md` - LangGraph agent flow with ReAct loop
- `auth-flow.md` - JWT authentication flow
- `chat-api-flow.md` - Chat API sequence with tool events
- `database-erd.md` - Database schema
- `llm-providers.md` - LLM provider abstraction with tool-calling methods
- `memory-flow.md` - Memory system flow
- `streaming-flow.md` - SSE streaming flow with tool_use events
- `tool-system.md` - Tool registry, web search, and adding new tools
- `slack-flow.md` - Slack integration flow
- `frontend-architecture.md` - Frontend component architecture

### When to Update Documentation
- After completing a phase, ensure diagrams reflect the implementation
- When adding new APIs, create sequence diagrams
- When modifying architecture, update the architecture diagram
- Include diagrams in the phase task file if helpful

## Coding Standards

### Python (Backend)
- Use type hints for all functions
- Follow PEP 8, enforce with ruff
- Async functions for I/O operations
- Pydantic models for request/response schemas
- Write tests BEFORE implementation (TDD)

### TypeScript (Frontend)
- Strict TypeScript mode
- Functional components with hooks
- React Query for server state
- Write tests alongside components

### Testing Requirements
- All new code requires tests
- Backend: pytest with async support
- Frontend: Jest + React Testing Library
- Minimum 80% coverage for new code

### Git Workflow
- Feature branches from main
- Descriptive commit messages
- PR required for main branch

## Architecture Decisions

### LangGraph Agent Pattern
- Alfred is the router agent
- Sub-agents can be added in `backend/app/agents/`
- Tools are registered via decorators
- State persisted in Postgres via checkpoints

### Memory System
- Short-term: Redis (session context)
- Long-term: Postgres + pgvector (preferences, knowledge, summaries)
- Memory extraction runs after each conversation

### Slack Integration
- Thread-based sessions (thread_ts = session identifier)
- Cross-channel sync enabled
- Responses from webapp mirror to Slack

### Focus Mode Vocabulary
- **Alfred user**: The Alfred user who has focus mode enabled
- **Sender**: The Slack user who DMs or @mentions the Alfred user, triggering an auto-reply
- **VIP**: A sender who is allowed to bypass an Alfred user's focus session (no auto-reply sent)

## Environment Variables

### Backend
```
DATABASE_URL=postgresql://user:pass@localhost:5432/alfred
REDIS_URL=redis://localhost:6379
VERTEX_PROJECT_ID=your-gcp-project
VERTEX_LOCATION=us-central1
DEFAULT_LLM=gemini-1.5-pro
TAVILY_API_KEY=tvly-...
WEB_SEARCH_SYNTHESIS_MODEL=gemini-2.5-flash
BART_API_KEY=MW9S-E7SL-26DU-VV8V  # public demo key, register at api.bart.gov for production
SLACK_BOT_TOKEN=xoxb-...
SLACK_SIGNING_SECRET=...
JWT_SECRET=...
# Required Slack Bot Scopes: reactions:write (for thinking reaction indicator).
# Add under OAuth & Permissions > Bot Token Scopes at https://api.slack.com/apps,
# then reinstall the app. Without this scope, Alfred falls back to a text
# "working on it" message instead of a reaction.
```

### Frontend
```
VITE_API_URL=http://localhost:8000
VITE_GOOGLE_CLIENT_ID=...
```

## Deployment

- Container-agnostic design
- Primary target: GCP Cloud Run
- CI/CD via GitHub Actions
- See `docker-compose.yml` for production config

## Common Tasks

### Add a New Agent
1. Create agent file in `backend/app/agents/`
2. Define LangGraph state and nodes
3. Register with Alfred router
4. Add tests
5. Update CLAUDE.md if needed

### Add a New Tool
1. Create tool class extending `BaseTool` in `backend/app/tools/`
2. Define `name`, `description`, and `parameters_schema` (JSON Schema)
3. Implement `async def execute(self, **kwargs) -> str`
4. Register in `get_tool_registry()` in `backend/app/tools/registry.py`
5. Add display mapping in `frontend/src/components/chat/ToolStatusIndicator.tsx`
6. Add tests in `backend/tests/test_tools.py`
7. See `.claude/diagrams/tool-system.md` for architecture details

### Add a New API Endpoint
1. Create route in `backend/app/api/`
2. Add Pydantic schemas
3. Write tests first (TDD)
4. Implement endpoint
5. Update OpenAPI docs

### Add a Frontend Component
1. Create component in `frontend/src/components/`
2. Write tests alongside
3. Use shadcn/ui primitives where possible
4. Export from index file
