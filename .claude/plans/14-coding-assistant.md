# Coding Assistant Feature — Implementation Plan

## Context

Alfred currently has a GitHub App integration (OAuth + PAT, encrypted tokens, multi-account) but no coding capabilities. This feature lets users ask Alfred to work on coding tasks by launching ephemeral Docker containers running Claude Code. The flow is two-gated with **deterministic button-based approvals** (not LLM-driven). Containers are short-lived, locked down, and destroyed after each phase. After implementation, a separate adversarial review container audits the work before the user is notified.

## Architecture Overview

```
User (Web UI / Slack)
  ↕ (buttons for approval, SSE for updates)
Backend (FastAPI + LangGraph agent)
  ↕ (HTTP — internal network only, API-key authenticated)
Sandbox Orchestrator ("alfred-sandbox" in compose)
  ↕ (Docker API via socket)
Ephemeral Containers (allowlisted image only)
  ├── Planning container
  ├── Implementation container
  └── Adversarial review container
  ↕ (HTTPS — GitHub API, Vertex AI, package registries only)
```

**Key decisions:**
- **Deterministic approval gates:** Approvals happen via UI buttons and Slack interactive buttons — the LLM never triggers planning or implementation on its own
- **Sidecar name:** `alfred-sandbox` — general-purpose container orchestrator for future extensibility
- **Single multi-lang image:** Python + Node + common tools in one image
- **Container lockdown:** Non-root, network restricted to GitHub API + Vertex AI + package registries (PyPI, npm, etc.), image allowlist on sidecar
- **Adversarial review:** Separate container reviews the work after implementation, before user notification
- **Code Q&A:** Users can ask questions about a codebase — clones repo into container for full exploration
- **Repo confirmation:** Agent always confirms which repo to work against, never assumes

---

## Phase 1: Database + Tool + Deterministic Approval Flow

### 1.1 CodingJob Model

**New file:** `backend/app/db/models/coding_job.py`

| Column | Type | Purpose |
|---|---|---|
| `id` | UUID PK | |
| `user_id` | UUID FK → users | Owner |
| `session_id` | UUID FK → sessions | Conversation where initiated |
| `status` | String(30) | See status enum below |
| `mode` | String(20) | `plan`, `implement`, `review`, `explore` |
| `repo_full_name` | String(255) | `owner/repo` |
| `branch_name` | String(255) | Set when planning starts |
| `pr_url` | Text | Set when PR opens |
| `pr_number` | Integer | |
| `task_description` | Text | User's original request |
| `plan_content` | Text | Plan returned by Claude Code |
| `review_content` | Text | Adversarial review findings |
| `revision_of_job_id` | UUID FK → coding_jobs | Links revisions to original |
| `container_id` | String(100) | Current/last container ID |
| `error_details` | Text | Error info if failed |
| `github_account_label` | String(100) | Which GitHub connection |
| `conversation_log` | Text | Claude Code session log |
| `slack_channel_id` | String(100) | Slack channel for thread updates |
| `slack_thread_ts` | String(50) | Slack thread timestamp for all updates |
| `started_at` | DateTime | Container launch time |
| `completed_at` | DateTime | Container finish time |

**Status values:** `pending_plan_approval`, `planning`, `plan_ready`, `pending_impl_approval`, `implementing`, `reviewing`, `complete`, `failed`, `cancelled`, `exploring`

**Also create:** Repository (`coding_job.py`), Schemas (`coding_job.py`), Alembic migration.

### 1.2 CodingAssistant Tool

**New file:** `backend/app/tools/coding_assistant.py`

Pattern: action-based tool like `FocusModeTool` (`backend/app/tools/focus_mode.py`).

**LLM-facing actions only:**

```python
parameters_schema = {
    "type": "object",
    "properties": {
        "action": {
            "type": "string",
            "enum": ["propose", "ask_codebase", "status", "cancel"],
        },
        "repo": {"type": "string", "description": "GitHub repo in owner/repo format. REQUIRED — always ask the user if not specified."},
        "task_description": {"type": "string"},
        "question": {"type": "string", "description": "Question to ask about the codebase (for ask_codebase action)"},
        "account_label": {"type": "string"},
    },
    "required": ["action"],
}
```

**Action behaviors:**

```
action="propose":
  1. Validate repo is specified — if not, return error telling LLM to ask user
  2. Validate user has GitHub connection for the repo
  3. Create CodingJob row (status: pending_plan_approval)
  4. Return structured metadata with job_id, repo, task_description
  5. Frontend renders this as a card with "Approve Planning" / "Cancel" buttons
  → The LLM CANNOT advance the job. Only button clicks can.

action="ask_codebase":
  1. Validate repo is specified
  2. Create CodingJob row (status: exploring, mode: explore)
  3. Generate GitHub token, call sidecar to launch container in explore mode
  4. Enqueue ARQ poll task
  5. Return "Exploring the codebase, I'll share what I find shortly"

action="status":
  1. Look up active jobs for this user/session
  2. Return current status, plan content, PR URL, review findings

action="cancel":
  1. Cancel active job, kill container via sidecar if running
```

**Critical: The tool NEVER triggers planning or implementation.** The `propose` action only creates the job and returns metadata. Approval buttons (in frontend and Slack) call dedicated API endpoints that trigger the actual work.

**Register in:** `backend/app/tools/registry.py` (conditional on GitHub App config + sidecar URL being configured)

### 1.3 Deterministic Approval Gates (Button-Based)

**This is NOT agent-driven.** Approvals are handled by dedicated API endpoints called by UI buttons and Slack interactive buttons.

**Gate 1 — Plan approval:**

1. Tool `propose` action creates job with `status: pending_plan_approval`
2. Tool returns metadata including `job_id` → frontend renders approval card
3. In Slack: post message with "Approve Planning" / "Cancel" buttons
4. User clicks button → `POST /api/coding-jobs/{id}/approve-plan`
5. Endpoint calls `CodingJobService.start_planning(job_id)` → launches container
6. Job status → `planning`
7. When container completes → status → `plan_ready`, user notified with plan content

**Gate 2 — Implementation approval:**

1. Plan notification includes "Approve Implementation" / "Request Changes" / "Cancel" buttons
2. User clicks button → `POST /api/coding-jobs/{id}/approve-impl`
3. Endpoint calls `CodingJobService.start_implementation(job_id)` → launches container
4. Job status → `implementing`
5. When container completes → status → `reviewing`, adversarial review container auto-launches
6. When review completes → status → `complete`, user notified with PR URL + review findings

**Revision flow:**
1. User can request changes from conversation or via a "Request Changes" button on a completed job
2. `POST /api/coding-jobs/{id}/request-revision` with change description
3. Creates new CodingJob linked via `revision_of_job_id`, inherits branch/PR info
4. Follows same button-gated flow (can skip planning if user chooses "Implement Directly")

### 1.4 System Prompt Instructions

Add to `build_prompt_messages()` in `backend/app/agents/nodes.py` (~line 177):

```
"When the user asks you to write code, fix a bug, implement a feature, or make changes
in a GitHub repository, use the coding_assistant tool with action='propose'.
IMPORTANT: You MUST ask the user which repo to work on if they haven't specified one.
Never assume the repository. After proposing, tell the user that approval buttons will
appear for them to review and approve. You cannot start the work yourself — only the
user can approve via the buttons.

When the user asks questions about a codebase or wants to understand how something works
in a repo, use the coding_assistant tool with action='ask_codebase'. Again, always confirm
which repo to query."
```

Also inject active job context when a coding job exists for the session:
```python
coding_job_context = await redis.get(f"coding_job:{session_id}")
if coding_job_context:
    # Inject job status so LLM can inform user about progress
    system_content += f"\n\n**Active coding job:** {job_status_summary}"
```

---

## Phase 2: Sandbox Orchestrator Service (`alfred-sandbox`)

**New directory:** `sandbox/`

Lightweight FastAPI app. The ONLY service with Docker socket access.

### Endpoints

| Method | Path | Purpose |
|---|---|---|
| POST | `/jobs` | Launch container |
| GET | `/jobs/{id}` | Status + exit code |
| GET | `/jobs/{id}/output` | Plan/review/exploration output |
| DELETE | `/jobs/{id}` | Force-kill and remove container |
| GET | `/health` | Health check |

### Image Allowlist

The sidecar maintains a hardcoded allowlist of images it will run:

```python
ALLOWED_IMAGES = {
    "alfred-claude-code:latest",  # The only image allowed
}
```

Any request to launch an image not in this list is rejected with 403. This prevents the backend (even if compromised) from launching arbitrary containers.

### Container Launch Configuration

When launching a container, the sidecar enforces:

```python
container = docker_client.containers.run(
    image=validated_image,
    user="1000:1000",  # Non-root
    mem_limit="4g",
    cpu_quota=200000,  # 2 CPUs
    network_mode="sandbox-net",  # Restricted network
    stop_timeout=1800,  # 30 min max
    environment={...},
    volumes={output_dir: {"bind": "/output", "mode": "rw"}},
    detach=True,
    remove=False,  # Keep for log retrieval, cleanup after
)
```

### Network Restrictions

Create a custom Docker network `sandbox-net` with restricted egress:

```yaml
# In docker-compose
networks:
  sandbox-net:
    driver: bridge
    internal: false  # Needs egress but restricted via iptables/firewall rules
```

Allowed destinations (configured via container firewall or network policy):
- `github.com`, `api.github.com` — git operations + PR creation
- `*.googleapis.com` — Vertex AI API
- `pypi.org`, `files.pythonhosted.org` — Python packages
- `registry.npmjs.org` — npm packages
- `registry.yarnpkg.com` — Yarn packages

All other outbound traffic blocked.

### Security
- Listens only on internal Docker network (no port mapping to host)
- Authenticated via `SIDECAR_API_KEY` header
- Image allowlist enforced
- Resource limits enforced on every container
- Cleanup: remove containers + output dirs after results are read

### docker-compose additions (dev + prod)

```yaml
alfred-sandbox:
  build: ./sandbox
  volumes:
    - /var/run/docker.sock:/var/run/docker.sock
    - sandbox_workspaces:/workspaces
  environment:
    - SIDECAR_API_KEY=${SANDBOX_API_KEY}
  networks:
    - default
  # No port mapping — internal only
```

---

## Phase 3: Claude Code Container Image

**New directory:** `containers/claude-code/`

### Dockerfile (Multi-Language)

```dockerfile
FROM ubuntu:22.04

# System deps
RUN apt-get update && apt-get install -y \
    git curl wget gnupg2 ca-certificates build-essential \
    && rm -rf /var/lib/apt/lists/*

# Python (3.11 + pip + uv)
RUN apt-get update && apt-get install -y python3.11 python3-pip \
    && pip install uv \
    && rm -rf /var/lib/apt/lists/*

# Node.js 20
RUN curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y nodejs \
    && rm -rf /var/lib/apt/lists/*

# Claude Code CLI
RUN npm install -g @anthropic-ai/claude-code

# GitHub CLI (for PR creation)
RUN curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg \
    | dd of=/usr/share/keyrings/githubcli-archive-keyring.gpg \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" \
    | tee /etc/apt/sources.list.d/github-cli.list \
    && apt-get update && apt-get install -y gh

# GCP SDK (for Vertex AI auth)
RUN curl -sSL https://sdk.cloud.google.com | bash -s -- --disable-prompts
ENV PATH="/root/google-cloud-sdk/bin:$PATH"

# Non-root user
RUN useradd -m -u 1000 coder
USER coder
WORKDIR /workspace

COPY --chown=coder:coder entrypoint.sh /entrypoint.sh
COPY --chown=coder:coder block-sensitive-paths.sh /usr/local/bin/block-sensitive-paths.sh
RUN chmod +x /entrypoint.sh /usr/local/bin/block-sensitive-paths.sh

ENTRYPOINT ["/entrypoint.sh"]
```

### entrypoint.sh

Modes: `plan`, `implement`, `review`, `explore`

**All modes:**
1. Configure git: `git config --global url."https://x-access-token:${GITHUB_TOKEN}@github.com/".insteadOf "https://github.com/"`
2. Clone repo: `git clone --depth=50 https://github.com/${REPO}.git /workspace/repo`
3. `cd /workspace/repo`

**Plan mode (`MODE=plan`):**
1. Checkout default branch
2. Run Claude Code: `claude --print --output-format json "Given this repository, create a detailed implementation plan for: ${TASK_DESCRIPTION}. Output the plan in markdown." > /output/plan.md`
3. Copy conversation log to `/output/conversation.log`
4. Exit

**Implement mode (`MODE=implement`):**
1. Create/checkout branch: `git checkout -b ${BRANCH}`
2. Install pre-commit hook via `block-sensitive-paths.sh`
3. Write plan to `PLAN.md` for Claude Code context
4. Run Claude Code: `claude "Implement the following plan completely. Commit your changes with clear messages. Plan: ${PLAN_CONTENT}"`
5. Push branch: `git push origin ${BRANCH}`
6. Create draft PR: `gh pr create --draft --title "${PR_TITLE}" --body "${PR_BODY}"`
7. Write `{"pr_url": "...", "pr_number": N, "branch": "..."}` to `/output/result.json`
8. Copy conversation log to `/output/conversation.log`
9. Exit

**Review mode (`MODE=review`):**
1. Checkout the implementation branch
2. Get the diff: `git diff origin/${DEFAULT_BRANCH}...HEAD`
3. Run Claude Code: `claude --print "You are an adversarial code reviewer. Review the following changes against the original task. Check for: correctness, security issues, missed requirements, code quality, potential bugs, and edge cases. Be thorough and critical. Task: ${TASK_DESCRIPTION}. Plan: ${PLAN_CONTENT}. Changes are on branch ${BRANCH}." > /output/review.md`
4. Exit

**Explore mode (`MODE=explore`):**
1. Checkout default branch
2. Run Claude Code: `claude --print "${QUESTION}" > /output/answer.md`
3. Exit

### block-sensitive-paths.sh (Pre-commit Hook)

```bash
#!/bin/bash
# Installed as .git/hooks/pre-commit
SENSITIVE_PATHS="${SENSITIVE_PATHS:-.github/workflows,Dockerfile,docker-compose,.env,.secrets,*.pem,*.key}"
IFS=',' read -ra PATTERNS <<< "$SENSITIVE_PATHS"
STAGED=$(git diff --cached --name-only)
for file in $STAGED; do
  for pattern in "${PATTERNS[@]}"; do
    if [[ "$file" == *"$pattern"* ]]; then
      echo "BLOCKED: Cannot modify sensitive path: $file"
      exit 1
    fi
  done
done
```

Configurable via `SENSITIVE_PATHS` env var passed from the backend through the sidecar.

### Vertex AI Configuration
- `ANTHROPIC_VERTEX_PROJECT_ID` and `ANTHROPIC_VERTEX_REGION` as env vars
- GCP service account JSON mounted at `/credentials/gcp.json`
- `GOOGLE_APPLICATION_CREDENTIALS=/credentials/gcp.json`
- Claude Code natively supports Vertex AI

---

## Phase 4: Backend Integration

### 4.1 CodingJobService

**New file:** `backend/app/services/coding_job.py`

Orchestrates the full lifecycle. Analogous to `FocusModeOrchestrator` (`backend/app/services/focus_orchestrator.py`).

```python
class CodingJobService:
    async def create_proposal(user_id, session_id, repo, task_description, account_label) -> CodingJob
    async def start_planning(job_id) -> None  # Called by API endpoint on button click
    async def start_implementation(job_id) -> None  # Called by API endpoint on button click
    async def start_review(job_id) -> None  # Called automatically after implementation
    async def start_exploration(job_id) -> None  # Called by tool directly
    async def handle_container_complete(job_id, output) -> None  # Called by ARQ poll task
    async def cancel_job(job_id) -> None
    async def request_revision(job_id, change_description) -> CodingJob  # Creates new linked job
    async def _get_github_token(job) -> str  # Generates installation token
    async def _call_sidecar(mode, env_vars) -> str  # HTTP call to sandbox
```

### 4.2 GitHub Installation Tokens

**Extend:** `backend/app/services/github.py`

Add methods:
- `get_installation_token(installation_id: int) -> str` — Signs JWT with App private key, calls GitHub API for short-lived token (1hr)
- `get_installation_for_repo(user_id: str, repo_full_name: str) -> int` — Finds the installation ID for a repo

The GitHub App private key is already in Settings (`github_app_private_key` / `github_app_private_key_file`) but currently unused for JWT signing. This adds that capability.

### 4.3 ARQ Worker Task — Container Completion Detection

**How Alfred knows when a container is done:**

The ARQ worker task `poll_coding_job` polls the sandbox orchestrator every 15 seconds. The sandbox wraps `docker inspect` — when a container exits, its status changes from `running` to `exited` with an exit code. The poll task detects this and triggers the appropriate next step.

**Add to:** `backend/app/worker/tasks.py`

```python
async def poll_coding_job(ctx, job_id: str, container_id: str):
    """Poll sandbox for container completion. Re-enqueues itself until done."""
    # 1. GET /jobs/{container_id} from sandbox
    #    → Returns {status: "running"|"exited", exit_code: int|null}
    # 2. If status == "running" and under timeout → re-enqueue with 15s delay
    # 3. If status == "exited" and exit_code == 0:
    #    - Fetch output from GET /jobs/{container_id}/output
    #    - Call CodingJobService.handle_container_complete()
    #    - If mode was "implement" → auto-launch review container
    #    - If mode was "review" → mark complete, notify user with PR + review
    #    - Delete container via DELETE /jobs/{container_id}
    # 4. If status == "exited" and exit_code != 0 → mark failed, fetch logs, notify user
    # 5. If elapsed time > coding_job_timeout_minutes → kill container, mark failed
```

Register in `WorkerSettings.functions` (`backend/app/worker/main.py`).

### 4.4 API Endpoints (Button-Driven)

**New router:** `backend/app/api/coding_jobs.py`

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/coding-jobs` | List user's jobs (paginated) |
| GET | `/api/coding-jobs/{id}` | Job details + plan + review |
| POST | `/api/coding-jobs/{id}/approve-plan` | **Gate 1:** Start planning |
| POST | `/api/coding-jobs/{id}/approve-impl` | **Gate 2:** Start implementation |
| POST | `/api/coding-jobs/{id}/request-revision` | Request changes (body: `{description}`) |
| POST | `/api/coding-jobs/{id}/cancel` | Cancel job |

These are the ONLY way to advance a job past approval gates. The agent tool cannot call these.

### 4.5 Notifications + Slack Thread Lifecycle

**Every coding session creates a Slack thread**, regardless of whether it was initiated from the web UI or Slack.

**Web-initiated sessions:**
1. When `create_proposal()` is called, post a concise initial message to a configured Slack channel (e.g. `#alfred-coding` or user's DM with Alfred):
   ```
   🔧 Coding task proposed for `owner/repo`
   Task: {concise_description}
   🔗 View in Alfred: {web_ui_link_to_session}
   ```
2. Store the `slack_channel_id` and `slack_thread_ts` on the CodingJob row
3. All subsequent status updates, plan content, approval buttons, and review findings are posted as **replies to this thread**
4. User can approve/cancel from either the web UI or the Slack thread — both work

**Slack-initiated sessions:**
1. The thread already exists (user started the conversation in Slack)
2. Use the existing `slack_channel_id` and `slack_thread_ts` from the session
3. All updates go to the same thread

**Thread update messages:**
- Planning started: "Planning in progress..."
- Plan ready: Plan content + approval buttons (in thread)
- Implementation started: "Implementation in progress..."
- Review in progress: "Reviewing changes..."
- Complete: PR link + review findings + "Request Changes" button (in thread)
- Failed: Error details (in thread)

**Web UI notifications:**
- SSE event type `coding_job_update` with `{job_id, status, plan_content?, pr_url?, review_content?}`
- Updates the CodingJobCard in the conversation in real-time

### 4.6 Adversarial Review (Auto-Triggered)

After implementation container completes successfully:
1. `handle_container_complete()` detects `mode=implement`
2. Updates job status → `reviewing`
3. Launches a new container with `MODE=review` — same image, different entrypoint mode
4. Review container gets: branch name, task description, plan content
5. Claude Code reviews the diff adversarially
6. Output stored in `review_content` column
7. User notified with both PR link AND review findings
8. User can see review in conversation and decide whether to merge, request changes, or cancel

**Adversarial Review Prompt Requirements:**

The review prompt must be thorough and well-crafted. During implementation, invest significant effort into designing this prompt. It should cover:

- **Correctness:** Does the implementation actually fulfill every requirement in the original task description and plan? Call out any missed requirements or partial implementations.
- **Security:** Check for injection vulnerabilities, improper auth/authz, exposed secrets, unsafe deserialization, OWASP Top 10 issues, and any security anti-patterns.
- **Code quality:** Identify dead code, duplicated logic, poor naming, missing error handling at system boundaries, and violations of the repo's existing conventions (as defined in CLAUDE.md if present).
- **Edge cases & bugs:** Look for off-by-one errors, null/undefined handling, race conditions, resource leaks, and unhandled error paths.
- **Test coverage:** Were tests added? Do they cover the critical paths? Are there obvious gaps?
- **Architecture fit:** Does the implementation follow the repo's existing patterns, or does it introduce inconsistencies?

**Scope guardrails — the reviewer must NOT:**
- Suggest new features or enhancements beyond the original task
- Recommend "nice-to-have" improvements unrelated to the task
- Flag style preferences that don't affect correctness or security
- Propose refactors of code outside the diff

The review output should be structured with severity levels (critical / warning / note) so the user can quickly assess whether the PR is safe to merge or needs changes. The reviewer should give a clear pass/fail recommendation at the top.

---

## Phase 5: Frontend + Slack

### 5.1 Frontend

**ToolStatusIndicator.tsx:** Add `coding_assistant` with Code icon.

**Inline approval cards in message stream:**

When tool result metadata contains a coding job proposal:
```
┌─────────────────────────────────────┐
│ 🔧 Coding Task Proposed            │
│ Repo: owner/repo                    │
│ Task: Add user authentication...    │
│                                     │
│ [Approve Planning]  [Cancel]        │
└─────────────────────────────────────┘
```

When plan is ready:
```
┌─────────────────────────────────────┐
│ 📋 Plan Ready                       │
│ ▼ View Plan (collapsible)           │
│   1. Create auth middleware...      │
│   2. Add JWT validation...          │
│                                     │
│ [Approve Implementation] [Cancel]   │
└─────────────────────────────────────┘
```

When implementation + review complete:
```
┌─────────────────────────────────────┐
│ ✅ Implementation Complete          │
│ PR: owner/repo#42 (Draft)          │
│ ▼ View Review (collapsible)        │
│   ⚠ Consider adding input...       │
│                                     │
│ [Request Changes]                   │
└─────────────────────────────────────┘
```

Progress states show a spinner with status text.

**New components:**
- `CodingJobCard.tsx` — Renders job status, plan, review, buttons
- `useCodingJobs.ts` — React Query hooks for `/api/coding-jobs` endpoints

**SSE handling:** Handle `coding_job_update` events to update job cards in real-time without page refresh.

### 5.2 Slack Interactive Buttons

**Extend:** `handle_slack_interactive` in `backend/app/api/slack.py` (~line 993)

New action_ids:
- `coding_approve_plan` → calls `POST /api/coding-jobs/{id}/approve-plan`
- `coding_approve_impl` → calls `POST /api/coding-jobs/{id}/approve-impl`
- `coding_request_revision` → opens a dialog/modal for change description
- `coding_cancel` → calls `POST /api/coding-jobs/{id}/cancel`

Slack blocks posted at each gate:
```python
# Proposal
blocks = [
    section("🔧 *Coding Task Proposed*\n*Repo:* `{repo}`\n*Task:* {desc}"),
    actions([
        button("Approve Planning", "coding_approve_plan", job_id, style="primary"),
        button("Cancel", "coding_cancel", job_id),
    ])
]

# Plan ready
blocks = [
    section("📋 *Plan Ready*\n```{truncated_plan}```"),
    actions([
        button("Implement", "coding_approve_impl", job_id, style="primary"),
        button("Cancel", "coding_cancel", job_id),
    ])
]

# Complete with review
blocks = [
    section("✅ *PR Created:* {pr_url}\n\n*Review:*\n{review_summary}"),
    actions([
        button("Request Changes", "coding_request_revision", job_id),
    ])
]
```

---

## Phase 6: Configuration + Hardening

### Config additions (`backend/app/core/config.py`)

```python
# Sandbox orchestrator
sandbox_url: str = "http://alfred-sandbox:8080"
sandbox_api_key: str = ""
claude_code_image: str = "alfred-claude-code:latest"

# Coding assistant
coding_job_timeout_minutes: int = 30
coding_sensitive_paths: str = ".github/workflows,Dockerfile,docker-compose,.env"
coding_max_concurrent_jobs: int = 2  # Per user

# Vertex AI for Claude Code (may differ from Alfred's own Vertex config)
claude_code_vertex_project: str = ""
claude_code_vertex_region: str = "us-east5"
```

### Hardening
- Container timeout: kill after `coding_job_timeout_minutes`
- Orphan cleanup: sidecar removes containers older than 1hr on startup
- Rate limiting: max `coding_max_concurrent_jobs` per user
- Error recovery: container crash → mark failed, notify user with error context
- Audit trail: conversation logs stored on every job for PR review

---

## Critical Files to Modify

| File | Change |
|---|---|
| `backend/app/agents/nodes.py` (~line 177) | Add coding assistant system prompt instructions + active job context injection |
| `backend/app/tools/registry.py` | Register `CodingAssistantTool` |
| `backend/app/services/github.py` | Add `get_installation_token()`, `get_installation_for_repo()` |
| `backend/app/worker/main.py` | Register `poll_coding_job` task |
| `backend/app/worker/tasks.py` | Add `poll_coding_job` function |
| `backend/app/api/__init__.py` | Register coding_jobs router |
| `backend/app/api/slack.py` (~line 993) | Add interactive button handlers for coding approvals |
| `backend/app/core/config.py` | Add sandbox/coding config fields |
| `backend/app/db/models/__init__.py` | Register CodingJob model |
| `frontend/src/components/chat/ToolStatusIndicator.tsx` | Add coding_assistant display |
| `docker-compose.dev.yml` | Add alfred-sandbox service |
| `docker-compose.prod.yml` | Add alfred-sandbox service + sandbox-net network |

## New Files to Create

| File | Purpose |
|---|---|
| `backend/app/db/models/coding_job.py` | CodingJob model |
| `backend/app/db/repositories/coding_job.py` | Repository |
| `backend/app/schemas/coding_job.py` | Pydantic schemas |
| `backend/app/tools/coding_assistant.py` | Agent tool (propose, ask_codebase, status, cancel) |
| `backend/app/services/coding_job.py` | Job lifecycle service |
| `backend/app/api/coding_jobs.py` | REST endpoints (button-driven approvals) |
| `sandbox/main.py` | Sandbox orchestrator service |
| `sandbox/Dockerfile` | Sandbox image |
| `sandbox/requirements.txt` | Sandbox deps (FastAPI, docker, uvicorn) |
| `containers/claude-code/Dockerfile` | Multi-lang Claude Code image |
| `containers/claude-code/entrypoint.sh` | Container entrypoint (plan/implement/review/explore modes) |
| `containers/claude-code/block-sensitive-paths.sh` | Pre-commit hook for sensitive paths |
| `frontend/src/components/chat/CodingJobCard.tsx` | Job status/plan/review card with buttons |
| `frontend/src/hooks/useCodingJobs.ts` | React Query hooks |

## Implementation Order

1. **Phase 1:** DB model + migration + repository + schemas + tool + system prompt
2. **Phase 2:** Sandbox orchestrator service + docker-compose integration
3. **Phase 3:** Claude Code container image (Dockerfile + entrypoint + security hooks)
4. **Phase 4:** CodingJobService + GitHub tokens + ARQ polling + API endpoints + notifications
5. **Phase 5:** Frontend cards + Slack interactive buttons
6. **Phase 6:** Config + hardening + adversarial review integration

## Verification Plan

1. **Unit tests:** Tool actions, service methods, status transitions, image allowlist
2. **Integration tests:** API endpoints with real DB, mocked sidecar responses
3. **Sandbox tests:** Container lifecycle with mock Docker client
4. **Manual E2E (web):** Propose → button approve plan → review plan → button approve impl → verify review → verify PR
5. **Manual E2E (Slack):** Same flow via Slack interactive buttons
6. **Revision test:** Request changes → new container → commits to same branch
7. **Security tests:** Sensitive path blocking, non-root enforcement, image allowlist rejection, network restrictions
8. **Adversarial review test:** Verify review container catches intentional issues
9. **Code Q&A test:** Ask question about repo → get answer from container exploration
