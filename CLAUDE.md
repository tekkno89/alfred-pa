# Alfred AI Assistant - Claude Code Instructions

## Project Overview

Alfred is a personal AI assistant built with LangGraph, FastAPI, React, and Slack integration. See `.claude/plans/` for the current implementation plan and task tracking.

## Quick Reference

- **Backend:** `backend/` - FastAPI + LangGraph (Python 3.11+)
- **Frontend:** `frontend/` - React + Tailwind + shadcn/ui
- **Database:** PostgreSQL 16 + pgvector, Redis 7
- **LLM:** Vertex AI (Gemini + Claude, configurable)
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
uv run pytest                   # Run tests
uv run pytest --cov             # Run tests with coverage
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
- **02-agent-chat-api.md** - Phase 2: LangGraph agent, chat endpoints
- Additional phase files created as needed

### Workflow
1. Start each session by reading `00-project-overview.md` to understand current status
2. Read the relevant phase file for detailed tasks
3. Mark tasks `[x]` when complete
4. Update phase status in overview when phase completes
5. Add new tasks as they emerge

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

## Environment Variables

### Backend
```
DATABASE_URL=postgresql://user:pass@localhost:5432/alfred
REDIS_URL=redis://localhost:6379
VERTEX_PROJECT_ID=your-gcp-project
VERTEX_LOCATION=us-central1
DEFAULT_LLM=gemini-1.5-pro
SLACK_BOT_TOKEN=xoxb-...
SLACK_SIGNING_SECRET=...
JWT_SECRET=...
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
