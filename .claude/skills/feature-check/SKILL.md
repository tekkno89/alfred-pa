---
name: feature-check
description: Verify a feature implementation against the adding-a-feature checklist
allowed-tools: Read, Glob, Grep, Bash(git diff*), Bash(git log*)
argument-hint: [feature-name]
---

# Feature Implementation Checker

Verify that a feature implementation covers all required touch-points from the adding-a-feature checklist.

## Instructions

1. Read `.claude/guides/adding-a-feature.md` to load the full checklist.

2. Accept the feature name from the argument (e.g., `/feature-check todos`). If no argument is given, ask the user which feature to check.

3. Run `git diff main...HEAD --name-only` to see all files changed on the current branch. If the branch has no diff from main, check the working tree instead by looking at the full codebase for the feature.

4. For each checklist category below, check whether the relevant files exist and contain the expected patterns. Mark each as **DONE**, **MISSING**, or **N/A** (not applicable).

### Backend Checks

| Check | How to verify |
|-------|---------------|
| Database model | Glob for `backend/app/db/models/{feature}.py` |
| Model registered in `__init__.py` | Grep for the model import in `backend/app/db/models/__init__.py` |
| Alembic migration | Glob for `backend/alembic/versions/*{feature}*` |
| Repository | Glob for `backend/app/db/repositories/{feature}.py` |
| Pydantic schemas | Glob for `backend/app/schemas/{feature}.py` |
| API routes | Glob for `backend/app/api/{feature}.py` |
| Feature access check | Grep for `is_enabled.*card:{feature}` in the API file |
| Router registered | Grep for `{feature}_router` in `backend/app/api/__init__.py` |
| Available-cards registration | Grep for `card:{feature}` in `backend/app/api/dashboard.py` |

### Frontend Checks

| Check | How to verify |
|-------|---------------|
| TypeScript types | Grep for the feature's type names in `frontend/src/types/index.ts` |
| React Query hooks | Glob for `frontend/src/hooks/use{Feature}.ts` (PascalCase) |
| Cache invalidation | Grep for `invalidateQueries.*{feature}` in the hooks file |
| Dashboard card | Glob for `frontend/src/components/dashboard/{Feature}Card.tsx` |
| Card renderer registered | Grep for `{feature}` in `CARD_RENDERERS` in `frontend/src/pages/HomePage.tsx` |
| Card metadata registered | Grep for `{feature}` in `CARD_META` in `frontend/src/components/dashboard/DashboardConfigDialog.tsx` |
| Feature page | Glob for `frontend/src/pages/{Feature}Page.tsx` |
| Route in App.tsx | Grep for `{Feature}Page` in `frontend/src/App.tsx` |
| Admin feature toggle | Grep for `card:{feature}` in `frontend/src/pages/AdminPage.tsx` |

### Agent Tool Checks (if applicable)

| Check | How to verify |
|-------|---------------|
| Tool class | Glob for `backend/app/tools/{feature}.py` |
| Tool registered | Grep for the tool class name in `backend/app/tools/registry.py` |
| Tool display mapping | Grep for the tool name in `frontend/src/components/chat/ToolStatusIndicator.tsx` |
| System prompt instructions | Grep for the feature/tool name in `backend/app/agents/nodes.py` |

5. Output a summary table like this:

```
## Feature Check: {feature}

### Backend
| Item                          | Status  |
|-------------------------------|---------|
| Database model                | DONE    |
| Model in __init__.py          | DONE    |
| Alembic migration             | DONE    |
| Repository                    | DONE    |
| Pydantic schemas              | DONE    |
| API routes                    | DONE    |
| Feature access check          | MISSING |
| Router registered             | DONE    |
| Available-cards registration  | MISSING |

### Frontend
| Item                          | Status  |
|-------------------------------|---------|
| TypeScript types              | DONE    |
| React Query hooks             | DONE    |
| Cache invalidation            | DONE    |
| Dashboard card                | DONE    |
| Card renderer (CARD_RENDERERS)| DONE    |
| Card metadata (CARD_META)     | MISSING |
| Feature page                  | DONE    |
| Route in App.tsx              | DONE    |
| Admin toggle (FEATURE_KEYS)   | MISSING |

### Agent Tool
| Item                          | Status  |
|-------------------------------|---------|
| Tool class                    | DONE    |
| Tool registered               | DONE    |
| Tool display mapping          | MISSING |
| System prompt instructions    | DONE    |
```

6. After the table, add a **Commonly Missed Items** section that highlights any MISSING items from this list:
   - Feature access check in API endpoints
   - Available-cards registration in dashboard.py
   - Admin feature toggle in FEATURE_KEYS
   - Card metadata in CARD_META
   - Cache invalidation in mutation onSuccess
   - Tool display mapping in TOOL_DISPLAY
