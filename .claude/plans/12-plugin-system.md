# Phase 12: Plugin System — Installable Feature Modules

**Status:** Design / Brainstorm
**Priority:** Future

## Goal

Create a plugin architecture that allows features (e.g., MLB scores, weather, fitness tracking) to be developed in separate repos and installed into the Alfred codebase. Plugins are **not runtime dependencies** — they are scaffolded into the project at install time, becoming regular code in the repo. Think shadcn/ui, not npm packages.

This keeps the main repo clean of niche/personal features while maintaining a fully static, inspectable codebase with no dynamic discovery or runtime plugin loading.

---

## Design Principles

1. **Convention-based auto-discovery** — The app automatically loads routes, models, tools, and cards from their respective directories. Installing a plugin means copying files in; uninstalling means deleting them. No registration files to patch.
2. **Convention over configuration** — Plugins follow a strict directory/file structure. Each file exports expected names (`router`, `BaseTool` subclass, card metadata, etc.).
3. **Standard migrations** — Plugin models land in `backend/app/db/models/`, migrations generated via normal `alembic revision --autogenerate`.
4. **Reversible installs** — Uninstall is just deleting the plugin's files. No source code patching to reverse.
5. **Plugins can be API-only** — Not every plugin needs models, tools, or dashboard cards. Only provide what you need; discovery skips what isn't there.

---

## App Refactor: Auto-Discovery (Prerequisite)

Before plugins can work, the app needs to load features by directory convention instead of explicit imports. This is a one-time refactor that also simplifies adding first-party features.

### Backend Auto-Discovery

#### Routes — `backend/app/api/__init__.py`

Scan the `api/` directory for modules exporting a `router` variable. Use the module filename as the URL prefix.

```python
import importlib
import pkgutil

router = APIRouter()

# Auto-discover all routers in app.api.*
package = importlib.import_module("app.api")
for importer, module_name, is_pkg in pkgutil.iter_modules(package.__path__):
    if module_name.startswith("_"):  # skip __init__, _helpers, etc.
        continue
    module = importlib.import_module(f"app.api.{module_name}")
    if hasattr(module, "router"):
        # Use ROUTER_PREFIX if defined, otherwise use module name
        prefix = getattr(module, "ROUTER_PREFIX", f"/{module_name}")
        tags = getattr(module, "ROUTER_TAGS", [module_name])
        router.include_router(module.router, prefix=prefix, tags=tags)
```

Each route module exports:
```python
from fastapi import APIRouter
router = APIRouter()
ROUTER_PREFIX = "/mlb"        # optional, defaults to /module_name
ROUTER_TAGS = ["mlb"]         # optional, defaults to [module_name]
```

#### Models — `backend/app/db/models/__init__.py`

Scan the `models/` directory and import all modules so they register with `Base.metadata`:

```python
import importlib
import pkgutil

# Auto-discover all model modules
package = importlib.import_module("app.db.models")
for importer, module_name, is_pkg in pkgutil.iter_modules(package.__path__):
    if module_name.startswith("_"):
        continue
    importlib.import_module(f"app.db.models.{module_name}")
```

Alembic's `env.py` already does `from app.db.models import *` — the auto-import in `__init__.py` ensures all models are in `Base.metadata` when that runs.

#### Tools — `backend/app/tools/registry.py`

Scan the `tools/` directory for `BaseTool` subclasses:

```python
import importlib
import pkgutil
import inspect

def _register_default_tools(registry: ToolRegistry) -> None:
    package = importlib.import_module("app.tools")
    for importer, module_name, is_pkg in pkgutil.iter_modules(package.__path__):
        if module_name.startswith("_") or module_name in ("base", "registry"):
            continue
        module = importlib.import_module(f"app.tools.{module_name}")
        for name, obj in inspect.getmembers(module, inspect.isclass):
            if issubclass(obj, BaseTool) and obj is not BaseTool:
                try:
                    tool = obj()
                    if tool.is_available():  # tools can self-check config
                    registry.register(tool)
                except Exception:
                    pass  # skip tools that can't initialize
```

To handle conditional loading (e.g., web search needs `TAVILY_API_KEY`), add an `is_available()` method to `BaseTool`:

```python
class BaseTool(ABC):
    # ... existing fields ...

    def is_available(self) -> bool:
        """Override to check config/env. Return False to skip registration."""
        return True
```

```python
class WebSearchTool(BaseTool):
    def is_available(self) -> bool:
        return bool(get_settings().tavily_api_key)
```

#### Dashboard Available Cards — `backend/app/api/dashboard.py`

Instead of hard-coded `if` checks, scan for card types dynamically. Each route module can declare a card:

```python
# In any api module (e.g., api/mlb.py)
CARD_TYPE = "mlb"  # declares this module provides a dashboard card
```

The dashboard endpoint scans for these:

```python
@router.get("/available-cards", response_model=list[str])
async def get_available_cards(user: CurrentUser, db: DbSession) -> list[str]:
    repo = FeatureAccessRepository(db)
    cards: list[str] = []

    # Auto-discover card types from api modules
    package = importlib.import_module("app.api")
    for importer, module_name, is_pkg in pkgutil.iter_modules(package.__path__):
        module = importlib.import_module(f"app.api.{module_name}")
        card_type = getattr(module, "CARD_TYPE", None)
        if card_type and await repo.is_enabled(user.id, f"card:{card_type}"):
            cards.append(card_type)

    return cards
```

### Frontend Auto-Discovery

#### Plugin Manifests — `frontend/src/plugins/`

Each plugin (and existing feature with a card/page) gets a manifest file:

```
frontend/src/plugins/
  bart.ts
  todos.ts
  notes.ts
  calendar.ts
  mlb.ts          ← added by plugin install
```

Each manifest exports a standard shape:

```tsx
// frontend/src/plugins/mlb.ts
import { MlbCard } from '../components/mlb/MlbCard'
import { MlbPage } from '../pages/MlbPage'

export default {
  name: 'mlb',
  card: { type: 'mlb', component: MlbCard },
  routes: [{ path: '/mlb', component: MlbPage }],
}
```

A single index file auto-discovers all manifests using Vite's glob import:

```tsx
// frontend/src/plugins/index.ts
const modules = import.meta.glob('./*.ts', { eager: true })

export interface PluginCard {
  type: string
  component: React.ComponentType<{ preferences?: DashboardPreference }>
}

export interface PluginRoute {
  path: string
  component: React.ComponentType
}

export interface PluginManifest {
  name: string
  card?: PluginCard
  routes?: PluginRoute[]
}

export const plugins: PluginManifest[] = Object.values(modules)
  .map((m: any) => m.default)
  .filter(Boolean)
```

#### App.tsx — Dynamic Routes

```tsx
import { plugins } from './plugins'

// Inside Routes:
{plugins.flatMap(p =>
  (p.routes || []).map(r => (
    <Route key={r.path} path={r.path} element={<r.component />} />
  ))
)}
```

#### HomePage.tsx — Dynamic Card Rendering

Replace the hard-coded `CARD_RENDERERS` dict:

```tsx
import { plugins } from '../plugins'

// Build card renderers from plugin manifests
const pluginCards = Object.fromEntries(
  plugins
    .filter(p => p.card)
    .map(p => [p.card!.type, p.card!.component])
)

// In the render:
visibleCards.map(({ cardType, pref }) => {
  const CardComponent = pluginCards[cardType]
  if (!CardComponent) return null
  return <div key={cardType}><CardComponent preferences={pref} /></div>
})
```

---

## Plugin Structure Spec

A plugin repo must follow this layout:

```
alfred-plugin-mlb/
  plugin.json                          # manifest (used by install CLI)
  backend/
    api/mlb.py                         # FastAPI router
    schemas/mlb.py                     # Pydantic request/response models
    services/mlb.py                    # Business logic
    db/
      models/mlb.py                    # SQLAlchemy models (optional)
      repositories/mlb.py              # Data access layer (optional)
    tools/mlb.py                       # Agent tool (optional)
  frontend/
    plugins/mlb.ts                     # Plugin manifest (card + routes)
    components/mlb/                    # React components
      MlbCard.tsx                      # Dashboard card (optional)
      MlbCard.test.tsx
    pages/
      MlbPage.tsx                      # Full page (optional)
    hooks/
      useMlb.ts                        # React Query hooks
    types/
      mlb.ts                           # TypeScript types
```

### plugin.json Manifest

Used by the install CLI to know what to copy and what dependencies to install. The app itself never reads this file.

```json
{
  "name": "mlb",
  "display_name": "MLB Scores & Schedule",
  "description": "Live MLB scores, upcoming games, and team schedules",
  "version": "1.0.0",
  "backend": {
    "files": [
      "api/mlb.py",
      "schemas/mlb.py",
      "services/mlb.py",
      "db/models/mlb.py",
      "db/repositories/mlb.py",
      "tools/mlb.py"
    ],
    "dependencies": ["httpx"]
  },
  "frontend": {
    "files": [
      "plugins/mlb.ts",
      "components/mlb/",
      "pages/MlbPage.tsx",
      "hooks/useMlb.ts",
      "types/mlb.ts"
    ],
    "dependencies": {}
  },
  "env_vars": {
    "optional": [],
    "required": []
  }
}
```

---

## Installation Flow

### `alfred-plugin install ./alfred-plugin-mlb`

#### 1. Validate

- Read `plugin.json`, verify required fields
- Check no file conflicts (don't overwrite existing files unless `--force`)
- Check `plugins.lock` for already-installed plugins with the same name

#### 2. Copy Files

| Source (plugin repo)                | Destination (alfred codebase)                    |
|-------------------------------------|--------------------------------------------------|
| `backend/api/mlb.py`               | `backend/app/api/mlb.py`                         |
| `backend/schemas/mlb.py`           | `backend/app/schemas/mlb.py`                     |
| `backend/services/mlb.py`          | `backend/app/services/mlb.py`                    |
| `backend/db/models/mlb.py`         | `backend/app/db/models/mlb.py`                   |
| `backend/db/repositories/mlb.py`   | `backend/app/db/repositories/mlb.py`             |
| `backend/tools/mlb.py`             | `backend/app/tools/mlb.py`                       |
| `frontend/plugins/mlb.ts`          | `frontend/src/plugins/mlb.ts`                    |
| `frontend/components/mlb/`         | `frontend/src/components/mlb/`                   |
| `frontend/pages/MlbPage.tsx`       | `frontend/src/pages/MlbPage.tsx`                 |
| `frontend/hooks/useMlb.ts`         | `frontend/src/hooks/useMlb.ts`                   |
| `frontend/types/mlb.ts`            | `frontend/src/types/mlb.ts`                      |

That's it — no registration files to patch. The app discovers everything automatically.

#### 3. Install Dependencies

- Backend: `uv add <dependencies from manifest>`
- Frontend: `npm install <dependencies from manifest>`

#### 4. Generate Migration (if plugin has models)

```bash
cd backend && uv run alembic revision --autogenerate -m "add mlb plugin tables"
```

#### 5. Record Installation

Write to `plugins.lock` in the project root:

```json
{
  "installed": {
    "mlb": {
      "version": "1.0.0",
      "installed_at": "2026-03-09T...",
      "source": "/path/to/alfred-plugin-mlb",
      "files": [
        "backend/app/api/mlb.py",
        "backend/app/services/mlb.py",
        "frontend/src/plugins/mlb.ts",
        "..."
      ]
    }
  }
}
```

#### 6. Post-Install Messages

- List any required env vars the user needs to set
- Remind to run migrations: `alembic upgrade head`
- Remind to enable the feature in admin: `card:mlb`

---

## Uninstall Flow

### `alfred-plugin uninstall mlb`

1. Read `plugins.lock` to get file list
2. Delete all plugin files
3. Remove dependencies (if not shared with other plugins)
4. Warn about database tables (user should create a migration to drop them, or leave them)
5. Remove entry from `plugins.lock`

No source code patching to reverse — the app simply stops discovering the deleted files on next restart.

---

## Plugin Development Guide (for plugin authors)

### Backend Conventions

- **Router:** Export a variable named `router` (an `APIRouter` instance). Optionally export `ROUTER_PREFIX` and `ROUTER_TAGS`. Export `CARD_TYPE = "mlb"` if the plugin provides a dashboard card.
- **Models:** Extend `app.db.base.Base`. Prefix table names with your plugin name (e.g., `mlb_games`, `mlb_teams`) to avoid collisions.
- **Repositories:** Extend `app.db.repositories.base.BaseRepository` or follow the same pattern.
- **Services:** Accept `AsyncSession` as constructor arg. Use repositories for data access.
- **Tools:** Extend `app.tools.base.BaseTool`. Define `name`, `description`, `parameters_schema`, and implement `execute()`. Override `is_available()` if the tool requires specific config/env vars.
- **Schemas:** Use Pydantic v2 models for request/response.
- **Auth:** Use `CurrentUser` and `DbSession` dependency injection from `app.api.dependencies`.

### Frontend Conventions

- **Plugin Manifest:** Create `frontend/plugins/<name>.ts` exporting a default `PluginManifest` with card component and/or route definitions.
- **Dashboard Card:** Follow the existing card pattern (see `BartCard`, `TodosCard` for examples). Accept `preferences` prop.
- **Pages:** Use `AppLayout` conventions (page header, content area).
- **Hooks:** Use React Query (`useQuery`, `useMutation`) with `apiGet`/`apiPost` helpers.
- **Types:** Export interfaces for API response shapes.
- **Styling:** Use Tailwind + shadcn/ui components.

### What Plugins Can Depend On (stable internal APIs)

- `app.db.base.Base` — SQLAlchemy base class
- `app.db.session.get_db` — Database session dependency
- `app.api.dependencies.CurrentUser`, `DbSession` — Auth and DB injection
- `app.tools.base.BaseTool`, `ToolContext` — Tool base class
- `app.db.repositories.base` — Repository pattern
- `app.core.config.get_settings` — App settings access
- `app.services.encryption.TokenEncryptionService` — If storing tokens
- `frontend/src/lib/api.ts` — `apiGet`, `apiPost`, `apiPut`, `apiDelete` helpers
- `frontend/src/components/ui/` — shadcn/ui primitives

---

## Implementation Tasks

### Phase A: App Refactor — Auto-Discovery

One-time refactor to make the app discover features by convention.

**Backend:**
- [ ] Refactor `backend/app/api/__init__.py` to auto-discover routers from `app.api.*` modules
- [ ] Refactor `backend/app/db/models/__init__.py` to auto-import all model modules
- [ ] Add `is_available()` method to `BaseTool` base class (default returns `True`)
- [ ] Update `WebSearchTool` to use `is_available()` instead of registry-level config check
- [ ] Refactor `_register_default_tools()` to auto-discover `BaseTool` subclasses from `app.tools.*`
- [ ] Add `CARD_TYPE` export to existing api modules that provide cards (bart, notes, todos, calendar)
- [ ] Refactor `get_available_cards()` to auto-discover card types from api modules
- [ ] Verify all existing features still work after refactor
- [ ] Run full test suite

**Frontend:**
- [ ] Create `frontend/src/plugins/` directory
- [ ] Define `PluginManifest` TypeScript interface in `frontend/src/plugins/index.ts`
- [ ] Create plugin manifest files for existing features: `bart.ts`, `todos.ts`, `notes.ts`, `calendar.ts`
- [ ] Add `import.meta.glob` auto-discovery in `frontend/src/plugins/index.ts`
- [ ] Refactor `App.tsx` to render routes from plugin manifests (alongside existing static routes)
- [ ] Refactor `HomePage.tsx` to build card renderers from plugin manifests instead of `CARD_RENDERERS`
- [ ] Verify all existing features still work after refactor
- [ ] Run frontend tests

### Phase B: Plugin CLI Tool

- [ ] Create `scripts/alfred_plugin.py` (or `backend/app/cli/plugin.py`)
- [ ] Implement `install` command — validate manifest, copy files, install deps, record in lock file
- [ ] Implement `uninstall` command — delete files, remove deps, update lock file
- [ ] Implement `list` command — show installed plugins from lock file
- [ ] Implement `validate` command — check a plugin repo structure against the spec
- [ ] Handle idempotent installs (don't overwrite without `--force`)
- [ ] Handle missing optional sections (no models, no tools, no card, etc.)
- [ ] Print post-install reminders (env vars, migrations, admin toggle)

### Phase C: Plugin Template / Starter

- [ ] Create a template repo (`alfred-plugin-template`) with boilerplate
- [ ] Include example model, router, service, card, page, and plugin manifest
- [ ] Include a README with the plugin development guide
- [ ] Include a `plugin.json` with all optional fields documented

### Phase D: First Plugin (Proof of Concept)

- [ ] Build `alfred-plugin-mlb` as the first real plugin
- [ ] Validate the install/uninstall cycle end-to-end
- [ ] Verify migrations generate and apply correctly
- [ ] Verify dashboard card appears with feature access gating
- [ ] Verify agent tool works (if applicable)
- [ ] Document any spec changes discovered during implementation

### Phase E: Extract Existing Feature (Optional Validation)

- [ ] Extract BART into `alfred-plugin-bart` as a test
- [ ] Verify it can be uninstalled and reinstalled cleanly
- [ ] Confirm no regressions in the main app

---

## Open Questions

1. **Plugin updates** — When a plugin repo is updated, how do you upgrade? Options: (a) uninstall + reinstall (simplest, but loses local edits), (b) diff and merge (complex). For now, uninstall + reinstall is fine since migration compatibility is preserved (new migrations add to existing tables rather than drop/recreate).
2. **Dependency conflicts** — What if two plugins need different versions of the same package? Probably rare at this scale, but worth noting.
3. **Frontend nav/sidebar** — Should plugin manifests also declare sidebar nav items? Could extend `PluginManifest` with a `nav` field. The sidebar would consume the plugins array the same way routes and cards do.
4. **Plugin dependencies on other plugins** — Not needed initially, but worth considering if it ever comes up.
5. **Private dependencies** — If a plugin needs API keys or env vars, `plugin.json` should list them so the CLI can warn during install.

---

## Example: MLB Plugin Feature Set

For reference, the initial motivation for this system:

**Dashboard Card:**
- Select a favorite team
- Show next upcoming game (opponent, date/time, venue)
- When a game is in progress: live score, inning, outs, runners
- Quick link to full MLB page

**Full Page (`/mlb`):**
- League standings by division
- Today's scoreboard (all games)
- Team schedule (upcoming/recent for selected team)
- Game highlights/recaps (if API supports it)

**Data Source:** MLB Stats API (free, no key required) — `statsapi.mlb.com`
