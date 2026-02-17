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
     │  Port 443    │
     │  (HTTPS)     │
     │              │
     │    Nginx     │
     │              │
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

Two subdomains, both on port 443:

- **`alfred-slack.yourdomain.com`** → VM's public IP. Only `/api/slack/` is exposed — everything else returns 403.
- **`alfred.yourdomain.com`** → VM's Tailscale IP. Full access to the SPA and all API endpoints. Only reachable from your Tailscale network.
- **No PostgreSQL in the compose file** — uses an external database (Cloud SQL, RDS, etc.).
- **SSL** via Let's Encrypt with Cloudflare DNS-01 challenge (no port 80 needed for verification).

### External Resources

Before deploying, set up the following:

| Resource | Purpose |
|----------|---------|
| **VM** (e.g., GCE) | Runs Docker Compose |
| **PostgreSQL** (e.g., Cloud SQL) | Database with `pgvector` extension enabled |
| **Cloudflare** | DNS + SSL certificate verification (DNS-01 challenge) |
| **GCP Secret Manager** | Stores secrets (DB password, JWT secret, API keys) |
| **Tailscale** | Private network access to the web UI |
| **LLM provider** | Vertex AI or OpenRouter API access |

### GCP Setup

#### Service Account Roles

The VM's service account needs:

| Role | Purpose |
|------|---------|
| `Vertex AI User` | LLM inference (Gemini + Claude via Model Garden) |
| `Secret Manager Secret Accessor` | Fetching secrets at startup |

#### Firewall Rules

| Rule | Direction | Protocol/Port | Source | Purpose |
|------|-----------|---------------|--------|---------|
| `allow-http` | Ingress | TCP 80 | `0.0.0.0/0` | HTTP → HTTPS redirect |
| `allow-https` | Ingress | TCP 443 | `0.0.0.0/0` | Slack webhooks |
| `allow-tailscale` | Ingress | UDP 41641 | `0.0.0.0/0` | Tailscale direct connections (optional — works without via relay, but slower) |

SSH is handled by GCP's default `default-allow-ssh` rule, or use IAP tunneling (`gcloud compute ssh`).

Cloud SQL with private IP (`DB_HOST=10.x.x.x`) uses VPC peering — no firewall rule needed, just ensure the VM is in the same VPC.

```bash
gcloud compute firewall-rules create alfred-allow-http \
  --allow tcp:80 --source-ranges 0.0.0.0/0 --target-tags alfred

gcloud compute firewall-rules create alfred-allow-https \
  --allow tcp:443 --source-ranges 0.0.0.0/0 --target-tags alfred

gcloud compute firewall-rules create alfred-allow-tailscale \
  --allow udp:41641 --source-ranges 0.0.0.0/0 --target-tags alfred
```

Tag your VM with `alfred` to apply these rules.

#### Cloud SQL

Enable the pgvector extension:

```sql
CREATE EXTENSION IF NOT EXISTS vector;
```

### GCP Secret Manager

`deploy/start.sh` fetches secrets at startup. Create these secrets in your GCP project:

| Secret Name | Value |
|-------------|-------|
| `alfred-db-password` | PostgreSQL password |
| `alfred-jwt-secret` | Random string for JWT signing (`openssl rand -base64 32`) |
| `alfred-cloudflare-api-token` | Cloudflare API token (DNS edit permission) |
| `alfred-slack-bot-token` | Slack bot token (`xoxb-...`) |
| `alfred-slack-signing-secret` | Slack signing secret |
| `alfred-slack-app-token` | Slack app-level token (`xapp-...`) |
| `alfred-slack-client-secret` | Slack client secret (for OAuth) |
| `alfred-tailscale-authkey` | Tailscale auth key |
| `alfred-openrouter-api-key` | OpenRouter API key (optional) |
| `alfred-google-client-secret` | Google OAuth secret (optional) |

### DNS (Cloudflare)

Create two A records:

| Name | Type | Value |
|------|------|-------|
| `alfred-slack` | A | VM's public IP |
| `alfred` | A | VM's Tailscale IP |

The Tailscale IP is visible in the [Tailscale admin console](https://login.tailscale.com/admin/machines) after the container first starts.

#### Cloudflare API Token

Needed for SSL certificate issuance via DNS-01 challenge. Create at [Cloudflare Dashboard > My Profile > API Tokens](https://dash.cloudflare.com/profile/api-tokens):

1. Click **Create Token**
2. Use the **Edit zone DNS** template, or create a custom token with `Zone > DNS > Edit` permission
3. Restrict to your domain's zone
4. Store in GCP Secret Manager as `alfred-cloudflare-api-token`

### Tailscale

Tailscale provides private network access so the web UI is never exposed to the public internet.

1. Create an account at [login.tailscale.com](https://login.tailscale.com)
2. Install Tailscale on your devices (laptop, phone, etc.)
3. Generate an auth key at [Settings > Keys](https://login.tailscale.com/admin/settings/keys):
   - **Reusable**: Yes (survives container restarts)
   - **Ephemeral**: No (node should persist)
4. Store in GCP Secret Manager as `alfred-tailscale-authkey`

The `tailscale` service in `docker-compose.prod.yml` runs with `network_mode: host`, so the VM gets a Tailscale IP directly. No further configuration needed.

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

Edit `.env` with your non-secret configuration:

```bash
# LLM
DEFAULT_LLM=gemini-1.5-pro
VERTEX_PROJECT_ID=your-gcp-project
VERTEX_LOCATION=us-east5

# Domains
APP_DOMAIN=alfred.yourdomain.com
SLACK_DOMAIN=alfred-slack.yourdomain.com
FRONTEND_URL=https://alfred.yourdomain.com
CORS_ORIGINS=https://alfred.yourdomain.com

# Database connection (password fetched from Secret Manager)
DB_HOST=10.x.x.x       # Cloud SQL private IP
DB_PORT=5432
DB_NAME=alfred
DB_USER=alfred

# GCP
GCP_PROJECT_ID=your-gcp-project

# Auth
JWT_ALGORITHM=HS256
JWT_EXPIRATION_MINUTES=30

# Slack
SLACK_CLIENT_ID=your-slack-client-id
SLACK_OAUTH_REDIRECT_URI=https://alfred-slack.yourdomain.com/api/auth/slack/oauth/callback
```

Secrets (`JWT_SECRET`, `DATABASE_URL`, Slack tokens, etc.) are fetched from GCP Secret Manager by `start.sh` — don't add them to `.env` manually.

#### 4. SSL certificate

Get a Let's Encrypt certificate for both subdomains. The init script runs Certbot inside a container using Cloudflare DNS-01 challenge — no port 80 access or public DNS resolution needed:

```bash
sudo /opt/alfred/deploy/init-ssl.sh
```

The `certbot` container in the compose file handles automatic renewal every 12 hours.

#### 5. Start Alfred

```bash
sudo /opt/alfred/deploy/start.sh
```

This script:
1. Reads non-secret config from `.env`
2. Fetches secrets from GCP Secret Manager
3. Injects secrets into `.env` (between `# --- INJECTED SECRETS ---` markers)
4. Writes `deploy/cloudflare.ini` for certbot renewals
5. Runs `docker compose up -d`
6. Waits for the backend health check to pass

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
| `deploy/start.sh` | Main startup script. Fetches secrets, writes `.env` and `cloudflare.ini`, starts all services, waits for health check. |
| `deploy/init-ssl.sh` | One-time SSL setup. Runs Certbot DNS-01 challenge via Cloudflare to get a Let's Encrypt certificate for both subdomains. |
| `deploy/alfred.service` | Systemd unit file. Starts Alfred on boot via `start.sh`, stops via `docker compose down`. |
| `docker-compose.prod.yml` | Production compose file. Defines backend, worker, frontend (nginx), redis, certbot (dns-cloudflare), and tailscale services. |
| `frontend/Dockerfile.prod` | Multi-stage build: `npm run build` then serve with nginx. Uses `envsubst` to template domain variables into the nginx config. |
| `frontend/nginx.prod.conf` | Nginx config template. Three server blocks: HTTP redirect (80), app domain with full access (443), Slack domain with restricted access (443). |

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

AGPL-3.0 - See [LICENSE](LICENSE) for details.
