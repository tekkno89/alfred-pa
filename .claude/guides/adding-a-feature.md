# Adding a Feature — Complete Checklist

Use this checklist when building a new feature service (e.g., todos, notes, BART departures). Not every item applies to every feature — skip items that don't apply, but **review every item** to make a conscious decision.

---

## Backend

### 1. Database Model

- [ ] Create model in `backend/app/db/models/{feature}.py`
  - Extend `Base`, `UUIDMixin`, `TimestampMixin`
  - Add `user_id = Column(UUID, ForeignKey("users.id"), nullable=False)`
- [ ] Register model in `backend/app/db/models/__init__.py`
  - Add import and include in `__all__`

### 2. Alembic Migration

- [ ] Generate migration: `alembic revision --autogenerate -m "add {feature} table"`
- [ ] Review generated migration — verify both `upgrade()` and `downgrade()`
- [ ] If adding a non-nullable column to an existing table: add as nullable first, backfill, then alter to non-nullable (or use a server default)
- [ ] Test: `alembic upgrade head`, then `alembic downgrade -1`, then `alembic upgrade head`

### 3. Repository

- [ ] Create repository in `backend/app/db/repositories/{feature}.py`
  - Extend `BaseRepository[Model]` (from `backend/app/db/repositories/base.py`)
  - `BaseRepository` provides: `get()`, `get_multi()`, `count()`, `create()`, `update()`, `delete()`
- [ ] Add feature-specific queries:
  - `get_dashboard_items()` — items to display on dashboard card
  - `get_summary_counts()` — counts for dashboard summary (if applicable)
  - Any filtered/sorted list queries

### 4. Pydantic Schemas

- [ ] Create schemas in `backend/app/schemas/{feature}.py`
  - `{Feature}Create` — request body for creation
  - `{Feature}Update` — request body for updates (all fields optional)
  - `{Feature}Response` — single item response, use `ConfigDict(from_attributes=True)`
  - `{Feature}List` — paginated list response (if applicable)

### 5. API Routes

- [ ] Create router in `backend/app/api/{feature}.py`
- [ ] Standard CRUD endpoints: `POST /`, `GET /`, `GET /{id}`, `PUT /{id}`, `DELETE /{id}`
- [ ] Dashboard endpoints: `GET /summary`, `GET /dashboard`
- [ ] **COMMONLY MISSED — Feature access check** at start of every endpoint:
  ```python
  if user.role != "admin":
      enabled = await FeatureAccessRepository.is_enabled(db, user.id, "card:{feature}")
      if not enabled:
          raise HTTPException(status_code=403, detail="Feature not enabled")
  ```
- [ ] **Authorization check** — verify `item.user_id == user.id` in every endpoint that accesses a specific item
- [ ] **Register router** in `backend/app/api/__init__.py`:
  ```python
  from app.api.{feature} import router as {feature}_router
  router.include_router({feature}_router, prefix="/{feature}", tags=["{feature}"])
  ```

### 6. Dashboard Registration

- [ ] **COMMONLY MISSED — Register in available-cards** — add `card:{feature}` to `get_available_cards()` in `backend/app/api/dashboard.py`
  - Check `FeatureAccessRepository` for the user and include if enabled

---

## Frontend

### 7. TypeScript Types

- [ ] Add types in `frontend/src/types/index.ts`
  - Request types (`{Feature}Create`, `{Feature}Update`)
  - Response types (`{Feature}`, `{Feature}List`)

### 8. React Query Hooks

- [ ] Create hooks in `frontend/src/hooks/use{Feature}.ts`
- [ ] **COMMONLY MISSED — Cache invalidation in every mutation's `onSuccess`:**
  ```typescript
  onSuccess: () => {
    queryClient.invalidateQueries({ queryKey: ['{feature}'] })
  }
  ```
  Use a broad queryKey prefix to invalidate list, summary, and dashboard queries together.
- [ ] Add `refetchInterval: 60_000` for dashboard/real-time data queries

### 9. Dashboard Card

- [ ] Create card component in `frontend/src/components/dashboard/{Feature}Card.tsx`
  - Fetch data via dedicated hook (e.g., `use{Feature}Dashboard()`)
  - Show loading skeleton during initial load
  - Auto-refresh via `refetchInterval`
  - Include "View All" link to detail page
  - Optional quick-action buttons (e.g., "+" to create)
- [ ] **Register card renderer** in `CARD_RENDERERS` in `frontend/src/pages/HomePage.tsx`:
  ```typescript
  {feature}: () => <{Feature}Card />,
  ```
- [ ] **COMMONLY MISSED — Register card metadata** in `CARD_META` in `frontend/src/components/dashboard/DashboardConfigDialog.tsx`:
  ```typescript
  {feature}: { label: '{Feature Label}', icon: IconComponent },
  ```

### 10. Feature Page

- [ ] Create page in `frontend/src/pages/{Feature}Page.tsx`
- [ ] Add route in `App.tsx`

### 11. Admin Feature Toggle

- [ ] **COMMONLY MISSED — Add to `FEATURE_KEYS`** in `frontend/src/pages/AdminPage.tsx`:
  ```typescript
  { key: 'card:{feature}', label: '{Feature Label}' },
  ```

---

## Agent Tool (if the LLM needs to interact with this feature)

### 12. Tool Implementation

- [ ] Create tool class in `backend/app/tools/{feature}.py`
  - Extend `BaseTool`
  - Define `name`, `description`, and `parameters_schema` (JSON Schema format)
  - `execute()` receives `ToolContext` (db, user_id, timezone) — never trust LLM for auth
  - Return string results; set `self.last_execution_metadata` for streaming UI feedback
  - Return error strings instead of raising exceptions
- [ ] **Register tool** in `_register_default_tools()` in `backend/app/tools/registry.py`
- [ ] **COMMONLY MISSED — Tool display mapping** in `TOOL_DISPLAY` in `frontend/src/components/chat/ToolStatusIndicator.tsx`:
  ```typescript
  {tool_name}: { label: 'Doing something...', icon: SomeIcon },
  ```
- [ ] **System prompt instructions** — add tool usage guidelines to `build_prompt_messages()` in `backend/app/agents/nodes.py`

---

## Testing

### 13. Backend Tests

- [ ] Unit tests for tool logic (if applicable): `backend/tests/test_tools.py`
- [ ] Unit tests for service logic (if applicable): `backend/tests/services/`
- [ ] Integration tests for API endpoints: `backend/tests/api/` or `backend/tests/integration/`
  - Test both authorized and unauthorized access
  - Test feature access gate (403 when disabled, 200 when enabled)
  - Test ownership checks (403 when accessing another user's item)

### 14. Frontend Tests

- [ ] Component rendering tests
- [ ] Interaction tests (create, edit, delete flows)

---

## Quick Summary — Most Commonly Missed Steps

| Step | File |
|------|------|
| Feature access check in every API endpoint | `backend/app/api/{feature}.py` |
| Register in `get_available_cards()` | `backend/app/api/dashboard.py` |
| Admin feature toggle in `FEATURE_KEYS` | `frontend/src/pages/AdminPage.tsx` |
| Card metadata in `CARD_META` | `frontend/src/components/dashboard/DashboardConfigDialog.tsx` |
| Cache invalidation in mutation `onSuccess` | `frontend/src/hooks/use{Feature}.ts` |
| Tool display mapping in `TOOL_DISPLAY` | `frontend/src/components/chat/ToolStatusIndicator.tsx` |
