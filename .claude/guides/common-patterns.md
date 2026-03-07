# Common Patterns Reference

Broader patterns and design principles for the Alfred codebase. Reference this during implementation.

---

## Cache Invalidation

- **Broad invalidation**: `queryClient.invalidateQueries({ queryKey: ['todos'] })` catches list, summary, and dashboard queries that all start with the same prefix.
- **Cross-feature invalidation**: `useSetFeatureAccess` invalidates both `admin-user-features` AND `available-cards` so the dashboard updates immediately.
- **After OAuth redirects**: detect URL params (e.g., `?github_oauth=success`) and invalidate relevant queries.
- **Manual refresh buttons**: call `queryClient.invalidateQueries` directly on a refresh icon click.

---

## Feature Access / Authorization

- Feature keys follow the `card:{feature_name}` convention.
- Check via `FeatureAccessRepository.is_enabled(db, user_id, feature_key)`.
- Admin users (`user.role == "admin"`) bypass feature checks.
- Ownership check (`item.user_id != user.id` → 403) in every mutating endpoint.
- Frontend gates via `useAvailableCards()` hook — only render cards/pages for enabled features.

---

## Agent Tool Design

- **ToolContext** is set by `tool_node` from the authenticated session state — never from LLM output. Contains `db`, `user_id`, `timezone`.
- Tools return **plain text strings** (the LLM reads them to form a response).
- `last_execution_metadata` dict is streamed to the frontend as `tool_result` events for UI rendering.
- Max 3 tool iterations (ReAct loop) — last iteration forces text-only response.
- **Error handling**: catch exceptions, return error string, log with `logger.error()`. Never raise from `execute()`.
- **Lazy imports** in registry (`_register_default_tools`) to avoid circular dependencies.

---

## System Prompt Architecture

- Built fresh per message in `build_prompt_messages()` (`backend/app/agents/nodes.py`).
- Layers: base personality → date/time → tool instructions → memories → feature context.
- Memories retrieved via pgvector semantic search (top 5), appended as "Relevant context about the user:".
- Feature context injected dynamically (e.g., todo context from Slack thread mapping).

---

## OAuth / Integration Service Patterns

- **Flow**: backend generates auth URL → frontend redirects → provider callback → backend stores encrypted token.
- **Token storage**: always via `TokenEncryptionService` (envelope encryption with DEK/KEK).
- **Multi-account support**: `account_label` field (e.g., "personal", "work").
- **Frontend redirect handling**: detect URL params (`?{service}_oauth=success`), show toast, invalidate queries.
- **Token refresh**: implement `refresh_access_token()` with fallback to re-auth.
- **Cleanup**: `delete_connection()` with best-effort token revocation at the provider.
- **Reference implementations**: `backend/app/services/google_calendar.py`, `backend/app/api/github.py`.

---

## Slack Cross-Sync

- **Thread-based sessions**: `slack_thread_ts` is the session identifier.
- When a user sends a message via webapp, sync it to the Slack thread with attribution.
- When the AI responds, sync the response back to the Slack thread.
- Errors in sync are logged but **never raised** (don't fail the request over sync).
- Session source tracking: `session.source` = `'webapp'` or `'slack'`.

---

## External API Service Patterns

- Wrap external APIs in a service class: `backend/app/services/{service}.py`.
- Use `httpx.AsyncClient` for HTTP calls.
- Implement Redis caching with configurable TTL via `_get_cached()` / `_set_cached()` helpers.
- Return Pydantic models, not raw dicts.
- Handle API errors gracefully with logging.
- **Reference implementation**: `backend/app/services/bart.py`.

---

## Repository Pattern

- Extend `BaseRepository[Model]` from `backend/app/db/repositories/base.py`.
- `BaseRepository` provides: `get()`, `get_multi()`, `count()`, `create()`, `update()`, `delete()`.
- All methods async with `AsyncSession`.
- Add feature-specific queries: dashboard items, summary counts, filtered lists.

---

## Database Conventions

- Models use `UUIDMixin` (UUID PK) and `TimestampMixin` (`created_at`, `updated_at` with UTC server defaults).
- JSONB columns for flexible metadata (`preferences`, `metadata_`).

---

## Alembic Migration Patterns

- Sequential naming: `001_initial_schema.py`, `002_memory_vector.py`, etc.
- When adding a non-nullable column to an existing table: add as nullable first, backfill, then alter to non-nullable (or use a server default).
- Include both `upgrade()` and `downgrade()` functions.
- For new features: combine model table + indexes in a single migration.
- Test migrations: `alembic upgrade head` → `alembic downgrade -1` → `alembic upgrade head`.

---

## Streaming Events

- Events flow: `tool_node` → `stream_writer` → SSE → frontend.
- Event types: `token`, `tool_use`, `tool_result`, `done`, `error`.
- `tool_result` carries `tool_data` from `last_execution_metadata` for UI rendering.

---

## Error Handling Flow

| Layer | Pattern |
|-------|---------|
| **Tool errors** | Catch in `execute()`, return error string → LLM reads it and explains to user |
| **Agent/LLM errors** | Caught in `llm_node`, set `state["error"]` → stream `error` event to frontend |
| **API errors** | `HTTPException` with appropriate status codes (400, 403, 404, 500) |
| **Streaming errors** | Catch, yield `StreamEvent(type="error")`, end stream gracefully |
| **Frontend** | `ApiRequestError` class with status + detail, React Query handles retries |

---

## Dashboard Card Patterns

- Cards fetch their own data via dedicated hooks (e.g., `useTodoDashboard()`, `useBartDepartures()`).
- Show loading skeleton/spinner during initial load.
- Auto-refresh via `refetchInterval` (typically 60s).
- Optional manual refresh button using `queryClient.invalidateQueries`.
- Link to detail page from card (e.g., "View All" link).
- Quick-action buttons (e.g., "+" to create new item).

---

## Testing Patterns

- **Unit tests** (no DB): mock repositories and services, test tool logic, test API route logic.
  - Location: `backend/tests/test_tools.py`, `backend/tests/test_agent.py`, `backend/tests/services/`
- **Integration tests** (need Postgres): test full API request → DB → response.
  - Location: `backend/tests/integration/`, `backend/tests/api/`
  - Use test fixtures for DB session, authenticated user.
- **Frontend tests**: Jest + React Testing Library, test component rendering and interactions.
- When testing tools: mock the `ToolContext` with a test DB session and `user_id`.
- When testing API routes: test both authorized and unauthorized access, feature access checks.
- Always test the feature access gate (403 when disabled, 200 when enabled).
