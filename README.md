# Alfred AI Assistant

A personal AI assistant built with FastAPI, LangGraph, React, and Slack. Alfred handles conversations through a web interface and Slack, with features like long-term memory, focus mode (with Pomodoro), web search, and webhook integrations.

## Architecture

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│   Frontend   │────>│   Backend    │────>│   Slack API  │
│  React/Vite  │<────│   FastAPI    │<────│              │
└──────────────┘ SSE └──────┬───────┘     └──────────────┘
                            │
                 ┌──────────┼──────────┐
                 │          │          │
          ┌──────┴───┐ ┌───┴────┐ ┌───┴────┐
          │ Postgres │ │ Redis  │ │  LLM   │
          │ +pgvector│ │  (ARQ) │ │Provider│
          └──────────┘ └────────┘ └────────┘
```

- **Backend:** FastAPI + LangGraph agent with tool-calling (Python 3.11+)
- **Frontend:** React 18 + Tailwind CSS + Radix UI
- **Database:** PostgreSQL 16 with pgvector for semantic memory
- **Queue:** Redis 7 for caching and ARQ background jobs
- **LLM:** Configurable — OpenRouter, Vertex AI Gemini, or Vertex AI Claude

## Quick Start

### Prerequisites

- Docker and Docker Compose
- An LLM provider API key (see [LLM Configuration](#llm-configuration))

### 1. Clone and configure

```bash
git clone <repo-url> && cd alfred-pa
cp .env.example .env
```

Edit `.env` with at minimum:

```bash
# Pick one LLM provider (see LLM Configuration section below)
DEFAULT_LLM=openrouter/anthropic/claude-3.5-sonnet
OPENROUTER_API_KEY=sk-or-...

# Set a real secret for production
JWT_SECRET=change-me-to-a-random-string
```

### 2. Start services

```bash
docker-compose -f docker-compose.dev.yml up
```

### 3. Run database migrations

```bash
docker-compose -f docker-compose.dev.yml exec backend alembic upgrade head
```

### 4. Access

| Service | URL |
|---------|-----|
| Frontend | http://localhost:3000 |
| Backend API | http://localhost:8000 |
| API Docs (Swagger) | http://localhost:8000/docs |
| Grafana | http://localhost:3001 (admin/admin) |
| Prometheus | http://localhost:9090 |

Create an account at the frontend login page to get started.

## Project Structure

```
alfred-pa/
├── backend/
│   ├── app/
│   │   ├── agents/        # LangGraph agent (Alfred) and ReAct loop
│   │   ├── api/           # FastAPI route handlers
│   │   ├── core/          # Config, LLM providers, embeddings
│   │   ├── db/            # SQLAlchemy models, repositories, migrations
│   │   ├── schemas/       # Pydantic request/response models
│   │   ├── services/      # Slack service, notification service
│   │   ├── tools/         # Tool system (web search, registry)
│   │   └── worker/        # ARQ background tasks
│   ├── tests/
│   ├── pyproject.toml
│   └── Dockerfile.dev
├── frontend/
│   ├── src/
│   │   ├── components/    # React components (chat, focus, settings)
│   │   ├── hooks/         # Custom hooks (useChat, useAuth)
│   │   ├── lib/           # API client, utilities
│   │   ├── pages/         # Page components
│   │   └── types/         # TypeScript type definitions
│   ├── package.json
│   └── Dockerfile.dev
├── docker-compose.dev.yml
├── docker-compose.prod.yml
└── .env.example
```

## Configuration

All configuration is via environment variables. Copy `.env.example` to `.env` and fill in values.

### LLM Configuration

Alfred supports multiple LLM providers. Set `DEFAULT_LLM` to choose one:

| Provider | `DEFAULT_LLM` value | Required env vars |
|----------|---------------------|-------------------|
| OpenRouter | `openrouter/anthropic/claude-3.5-sonnet` | `OPENROUTER_API_KEY` |
| OpenRouter | `openrouter/google/gemini-pro-1.5` | `OPENROUTER_API_KEY` |
| Vertex AI Gemini | `gemini-1.5-pro` | `VERTEX_PROJECT_ID`, GCP credentials |
| Vertex AI Claude | `claude-3-5-sonnet@20240620` | `VERTEX_PROJECT_ID`, GCP credentials |

**OpenRouter** is the simplest option for local development — sign up at [openrouter.ai](https://openrouter.ai), create an API key, and set it in `.env`. It provides access to many models through a single API.

**Vertex AI** requires a GCP project with the Vertex AI API enabled. For local development, authenticate with `gcloud auth application-default login` or set `GOOGLE_APPLICATION_CREDENTIALS` to a service account key file. In production with Cloud Run, Workload Identity handles auth automatically.

### Web Search (Tavily)

Alfred can search the web when users ask about current events or recent information. The LLM autonomously decides when to search.

1. Sign up at [tavily.com](https://tavily.com) and get an API key
2. Add to `.env`:

```bash
TAVILY_API_KEY=tvly-...
```

That's it. When the key is present, Alfred automatically registers the web search tool. When the LLM decides to search, the frontend shows a "Searching the web..." indicator while results are fetched and synthesized.

Optional settings:

```bash
# Max number of search results to fetch (default: 5)
WEB_SEARCH_MAX_RESULTS=5

# Model used to synthesize search results into a summary (default: gemini-1.5-flash)
# Use a cheap/fast model here — it only summarizes search results
WEB_SEARCH_SYNTHESIS_MODEL=gemini-1.5-flash
```

If `TAVILY_API_KEY` is not set, web search is simply disabled and Alfred responds using only its training data.

### Slack Integration

Slack integration lets Alfred respond to DMs and @mentions, with cross-sync between the web UI and Slack threads.

#### 1. Create a Slack App

Go to [api.slack.com/apps](https://api.slack.com/apps) and create a new app **from scratch**.

#### 2. Bot Token Scopes

Under **OAuth & Permissions**, add these **Bot Token Scopes**:

- `app_mentions:read` — Receive @alfred mentions
- `chat:write` — Send messages
- `im:history` — Read DM messages
- `im:read` — Access DM channels
- `users:read` — Look up user info
- `users:read.email` — Look up user email for account linking

#### 3. Event Subscriptions

Under **Event Subscriptions**, enable events and set the Request URL:

```
https://yourdomain.com/api/slack/events
```

Subscribe to these **bot events**:
- `app_mention` — When someone @mentions Alfred
- `message.im` — When someone DMs Alfred

#### 4. Interactivity

Under **Interactivity & Shortcuts**, enable and set the Request URL:

```
https://yourdomain.com/api/slack/interactive
```

This handles interactive buttons (e.g., the "Urgent - Notify Them" bypass button in focus mode).

#### 5. Slash Commands

Under **Slash Commands**, create:

| Command | Request URL | Description |
|---------|-------------|-------------|
| `/alfred-link` | `https://yourdomain.com/api/slack/commands` | Link Slack to web account |
| `/alfred-focus` | `https://yourdomain.com/api/slack/commands` | Control focus mode |

`/alfred-focus` usage:
- `/alfred-focus on [minutes]` — Enable focus mode
- `/alfred-focus off` — Disable focus mode
- `/alfred-focus status` — Check status
- `/alfred-focus pomodoro [work_min/break_min/sessions]` — Start pomodoro

#### 6. Install and Configure

Install the app to your workspace, then add to `.env`:

```bash
SLACK_BOT_TOKEN=xoxb-...          # Bot User OAuth Token (from OAuth & Permissions page)
SLACK_SIGNING_SECRET=...          # Signing Secret (from Basic Information page)
SLACK_APP_TOKEN=xapp-...          # App-Level Token (from Basic Information > App-Level Tokens)
```

#### 7. Account Linking

Users link their Slack and web accounts by:
1. Running `/alfred-link` in Slack to get a one-time code (expires in 10 minutes)
2. Entering the code on the Settings page in the web UI

This enables cross-sync: messages sent in the web UI for a Slack-originated session are posted back to the Slack thread, and vice versa.

### Slack OAuth (for Focus Mode)

Focus mode can set your Slack status and enable Do Not Disturb. This requires a separate OAuth flow where the **user** (not just the bot) grants permissions.

#### 1. Add OAuth Redirect URL

Under **OAuth & Permissions** > **Redirect URLs**, add:

```
https://yourdomain.com/api/auth/slack/oauth/callback
```

#### 2. Add User Token Scopes

Under **OAuth & Permissions**, add these **User Token Scopes**:

- `users.profile:read` — Read current status (to restore later)
- `users.profile:write` — Set status during focus mode
- `dnd:write` — Enable Do Not Disturb
- `im:history` — Receive DM events for auto-reply
- `im:read` — Access DM channels for auto-reply

#### 3. Configure

Add to `.env`:

```bash
SLACK_CLIENT_ID=...               # From Basic Information page
SLACK_CLIENT_SECRET=...           # From Basic Information page
SLACK_OAUTH_REDIRECT_URI=https://yourdomain.com/api/auth/slack/oauth/callback
```

Users connect via the Settings page in the web UI.

### Authentication

Alfred uses email/password authentication with JWT tokens.

```bash
JWT_SECRET=your-secret-key        # Use a long random string in production
JWT_ALGORITHM=HS256               # Default, no need to change
JWT_EXPIRATION_MINUTES=30         # Token lifetime
```

### Database

Development uses Docker-managed PostgreSQL. No configuration needed for `docker-compose.dev.yml`.

For production, set:

```bash
DATABASE_URL=postgresql://user:password@host:5432/alfred
```

The database requires the `pgvector` extension (included in the `pgvector/pgvector:pg16` Docker image). For managed databases (Cloud SQL, RDS), enable the extension manually:

```sql
CREATE EXTENSION IF NOT EXISTS vector;
```

### Frontend

```bash
FRONTEND_URL=http://localhost:3000              # Used for OAuth redirects
CORS_ORIGINS=http://localhost:3000,http://localhost:5173  # Allowed CORS origins
VITE_API_URL=http://localhost:8000              # Backend URL (build-time)
```

## Features

### Chat with Memory

Alfred remembers facts and preferences across sessions using semantic memory backed by pgvector. Memories are automatically retrieved based on relevance to the current conversation.

Save memories explicitly:
- `/remember I prefer Python over JavaScript`
- `Remember that my team standup is at 9:30am`
- `Note that the production database is on us-east-1`

Manage memories in the web UI under the Memories page.

### Web Search

When `TAVILY_API_KEY` is configured, Alfred can search the web autonomously. The LLM decides when a query needs current information and calls the search tool. Results are synthesized into a concise summary with source citations.

### Focus Mode

Block distractions with timed focus sessions:

- **Simple mode:** Set a duration, get an auto-reply on Slack DMs
- **Pomodoro mode:** Alternating work/break intervals (default 25min/5min)
- **VIP list:** Designated users bypass focus mode
- **Slack integration:** Sets status, enables DND, auto-replies to messages
- **Webhooks:** Get notified of focus events via HTTP webhooks

### Webhooks

Subscribe to events via HTTP webhooks:

- `focus_started`, `focus_ended`
- `focus_bypass` (someone clicked urgent bypass)
- `pomodoro_work_started`, `pomodoro_break_started`

Configure on the Settings page. Payloads are JSON with event type, timestamp, and event-specific data.

## Local Development (without Docker)

### Backend

```bash
cd backend

# Install UV if needed
curl -LsSf https://astral.sh/uv/install.sh | sh

# Install dependencies
uv sync

# Run migrations
uv run alembic upgrade head

# Start the server
uv run uvicorn app.main:app --reload --port 8000

# Start the background worker (separate terminal)
uv run arq app.worker.WorkerSettings
```

Requires PostgreSQL and Redis running locally (or via Docker):

```bash
docker run -d --name alfred-postgres -p 5432:5432 \
  -e POSTGRES_USER=alfred -e POSTGRES_PASSWORD=alfred -e POSTGRES_DB=alfred \
  pgvector/pgvector:pg16

docker run -d --name alfred-redis -p 6379:6379 redis:7-alpine
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

### Running Tests

```bash
# Backend
cd backend
uv run pytest                     # All tests
uv run pytest tests/test_agent.py # Specific test file
uv run pytest --cov               # With coverage

# Frontend
cd frontend
npm test                          # Watch mode
npm run test:coverage             # With coverage
```

### Linting

```bash
# Backend
cd backend
uv run ruff check .
uv run ruff format .

# Frontend
cd frontend
npm run lint
```

## Production Deployment

The production stack runs on a VM with Docker Compose. It uses an external PostgreSQL database (e.g., Cloud SQL), Tailscale for private access, and Let's Encrypt for SSL.

### Architecture

```
         Internet
            │
     ┌──────┴──────┐
     │   Port 443   │──── Slack webhooks only
     │   (HTTPS)    │
     │              │
     │    Nginx     │
     │              │
     │   Port 3000  │──── Full app (SPA + API)
     │  (Tailscale) │
     └──────┬───────┘
            │
    ┌───────┼───────┐
    │       │       │
 Backend  Worker  Redis
    │       │
    └───┬───┘
        │
   Cloud SQL
  (PostgreSQL)
```

- **Port 80/443 (public):** HTTPS with Let's Encrypt. Only `/api/slack/` is exposed — everything else returns 403. HTTP redirects to HTTPS.
- **Port 3000 (Tailscale):** Full access to the SPA and all API endpoints. Only reachable from your Tailscale network.
- **No PostgreSQL in the compose file** — uses an external database (Cloud SQL, RDS, etc.).

### External Resources

Before deploying, set up the following:

| Resource | Purpose |
|----------|---------|
| **VM** (e.g., GCE, EC2) | Runs Docker Compose |
| **PostgreSQL** (e.g., Cloud SQL) | Database with `pgvector` extension enabled |
| **Domain + DNS** | A record pointing to the VM's public IP |
| **GCP Secret Manager** | Stores secrets (DB password, JWT secret, API keys) |
| **Tailscale** | Private network access to the web UI |
| **LLM provider** | Vertex AI or OpenRouter API access |

For Cloud SQL, enable the pgvector extension:

```sql
CREATE EXTENSION IF NOT EXISTS vector;
```

### GCP Secret Manager

`deploy/start.sh` fetches secrets from GCP Secret Manager at startup. Create these secrets in your GCP project:

| Secret Name | Value |
|-------------|-------|
| `alfred-db-password` | PostgreSQL password |
| `alfred-jwt-secret` | Random string for JWT signing |
| `alfred-slack-bot-token` | Slack bot token (`xoxb-...`) |
| `alfred-slack-signing-secret` | Slack signing secret |
| `alfred-slack-app-token` | Slack app-level token (`xapp-...`) |
| `alfred-slack-client-secret` | Slack client secret (for OAuth) |
| `alfred-tailscale-authkey` | Tailscale auth key |
| `alfred-openrouter-api-key` | OpenRouter API key (optional) |
| `alfred-google-client-secret` | Google OAuth secret (optional) |

The VM's service account needs the `Secret Manager Secret Accessor` role.

### VM Setup

#### 1. Install dependencies

```bash
# Docker
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER

# gcloud CLI (for Secret Manager access)
# https://cloud.google.com/sdk/docs/install
```

#### 2. Clone the repo

```bash
sudo git clone <repo-url> /opt/alfred
cd /opt/alfred
```

#### 3. Create the `.env` file

```bash
cp .env.example .env
```

Edit `.env` and fill in the non-secret configuration:

```bash
# LLM
DEFAULT_LLM=gemini-1.5-pro
VERTEX_PROJECT_ID=your-gcp-project
VERTEX_LOCATION=us-east5

# Networking
DOMAIN=yourdomain.com
FRONTEND_URL=https://yourdomain.com:3000
CORS_ORIGINS=http://localhost:3000

# Database connection details (password is fetched from Secret Manager)
DB_HOST=10.x.x.x       # Cloud SQL private IP
DB_PORT=5432
DB_NAME=alfred
DB_USER=alfred

# GCP project for Secret Manager
GCP_PROJECT_ID=your-gcp-project

# Auth
JWT_ALGORITHM=HS256
JWT_EXPIRATION_MINUTES=30

# Slack
SLACK_BOT_TOKEN=placeholder   # overwritten by start.sh
SLACK_SIGNING_SECRET=placeholder
SLACK_APP_TOKEN=placeholder
SLACK_CLIENT_ID=your-slack-client-id
SLACK_OAUTH_REDIRECT_URI=https://yourdomain.com/api/auth/slack/oauth/callback
```

You don't need to fill in secrets (`JWT_SECRET`, `DATABASE_URL`, `SLACK_*_SECRET`, etc.) — `start.sh` fetches those from GCP Secret Manager and injects them automatically.

#### 4. SSL certificate

Get a Let's Encrypt certificate by running the init script. This starts the nginx container on port 80, runs the ACME challenge inside the Certbot container, and stores the certificate in a Docker volume:

```bash
sudo /opt/alfred/deploy/init-ssl.sh
```

Nothing needs to be installed on the VM — Certbot runs as a container. After initial setup, the `certbot` container in the compose file handles automatic renewal every 12 hours.

#### 5. Start Alfred

```bash
sudo /opt/alfred/deploy/start.sh
```

This script:
1. Reads non-secret config from `.env`
2. Fetches secrets from GCP Secret Manager
3. Injects secrets into `.env` (between `# --- INJECTED SECRETS ---` markers)
4. Runs `docker compose up -d`
5. Waits for the backend health check to pass

#### 6. Set up the systemd service (optional)

To start Alfred automatically on boot:

```bash
sudo cp /opt/alfred/deploy/alfred.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable alfred
```

Then manage with:

```bash
sudo systemctl start alfred
sudo systemctl stop alfred
sudo systemctl restart alfred
sudo systemctl status alfred
journalctl -u alfred -f        # View logs
```

### Deploy Scripts Reference

| File | Purpose |
|------|---------|
| `deploy/start.sh` | Main startup script. Fetches secrets, writes `.env`, starts all services, waits for health check. |
| `deploy/init-ssl.sh` | One-time SSL setup. Starts nginx and runs the Certbot ACME challenge in a container to get a Let's Encrypt certificate. |
| `deploy/alfred.service` | Systemd unit file. Starts Alfred on boot via `start.sh`, stops via `docker compose down`. |
| `docker-compose.prod.yml` | Production compose file. Defines backend, worker, frontend (nginx), redis, certbot, and tailscale services. |
| `frontend/Dockerfile.prod` | Multi-stage build: `npm run build` then serve with nginx. Uses `envsubst` to template the domain into the nginx config. |
| `frontend/nginx.prod.conf` | Nginx config template. Three server blocks: HTTP redirect (80), HTTPS for Slack (443), Tailscale full app (3000). |

### Updating

```bash
cd /opt/alfred
sudo git pull
sudo docker compose -f docker-compose.prod.yml up -d --build
```

Or with the systemd service:

```bash
cd /opt/alfred
sudo git pull
sudo systemctl restart alfred
```

### Applying `.env` changes

Docker Compose only reads `env_file` when containers are created. To pick up `.env` changes:

```bash
docker compose -f docker-compose.prod.yml up -d --force-recreate backend worker
```

`docker compose restart` won't work — it reuses the existing container's environment.

## API Endpoints

| Group | Prefix | Description |
|-------|--------|-------------|
| Auth | `/api/auth` | Register, login, Slack linking, OAuth |
| Sessions | `/api/sessions` | Chat sessions CRUD, message streaming |
| Memories | `/api/memories` | Memory CRUD with semantic search |
| Focus | `/api/focus` | Focus mode, Pomodoro, VIP list |
| Slack | `/api/slack` | Event handling, slash commands |
| Webhooks | `/api/webhooks` | Webhook subscriptions |
| Notifications | `/api/notifications` | SSE event stream |

Full interactive docs at `http://localhost:8000/docs` when the backend is running.

## Observability

The dev stack includes:

- **Prometheus** (`:9090`) — Metrics collection, scraped from `/metrics`
- **Loki** (`:3100`) — Log aggregation
- **Grafana** (`:3001`) — Dashboards and alerting (default login: admin/admin)

## License

Private - All rights reserved
