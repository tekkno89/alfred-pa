# GitHub Integration Flow

## GitHub OAuth Flow

```mermaid
sequenceDiagram
    participant U as User
    participant FE as Frontend
    participant BE as Backend
    participant GH as GitHub
    participant DB as PostgreSQL

    U->>FE: Click "Connect with GitHub"
    FE->>FE: Show ConnectGitHubModal<br/>(account label + app config selector)
    U->>FE: Enter label, select app config, submit
    FE->>BE: GET /api/github/oauth/url?account_label=...&app_config_id=...
    BE->>BE: Resolve credentials (per-user config or global fallback)
    BE->>BE: Generate state token
    BE->>BE: Store state (user_id, account_label, app_config_id)
    BE-->>FE: {url: "https://github.com/login/oauth/authorize?..."}
    FE->>GH: Redirect to GitHub authorize URL

    U->>GH: Authorize Alfred app
    GH->>BE: GET /api/github/oauth/callback?code=...&state=...
    BE->>BE: Validate & consume state token
    BE->>BE: Resolve credentials from app_config_id in state
    BE->>GH: POST /login/oauth/access_token (exchange code)
    GH-->>BE: {access_token, refresh_token, scope, expires_in}
    BE->>GH: GET /user (fetch GitHub username)
    GH-->>BE: {login: "octocat"}
    BE->>BE: Encrypt access_token & refresh_token
    BE->>DB: Store UserOAuthToken (provider=github, github_app_config_id=...)
    BE->>FE: Redirect to /settings/integrations?github_oauth=success
    FE->>U: Show success feedback
```

## PAT (Personal Access Token) Flow

```mermaid
sequenceDiagram
    participant U as User
    participant FE as Frontend
    participant BE as Backend
    participant GH as GitHub
    participant DB as PostgreSQL

    U->>FE: Click "Add Token", enter PAT
    FE->>BE: POST /api/github/connections/pat {token, account_label}
    BE->>GH: GET /user (validate PAT)
    alt Valid token
        GH-->>BE: {login: "octocat"}
        BE->>BE: Encrypt PAT
        BE->>DB: Store UserOAuthToken (token_type=pat)
        BE-->>FE: GitHubConnectionResponse
        FE->>U: Show connection in list
    else Invalid token
        GH-->>BE: 401 Unauthorized
        BE-->>FE: 400 "Invalid token"
        FE->>U: Show error
    end
```

## Per-User GitHub App Config

```mermaid
flowchart TD
    A[_get_app_credentials] --> B{app_config_id<br/>provided?}
    B -->|Yes| C{Config found<br/>in DB?}
    C -->|Yes| D[Decrypt client_secret<br/>via DEK/KEK]
    D --> E[Return per-user<br/>client_id + client_secret]
    C -->|No| F{Global env vars<br/>configured?}
    B -->|No| F
    F -->|Yes| G[Return global<br/>client_id + client_secret]
    F -->|No| H[Raise ValueError<br/>No GitHub App configured]
```

## Multi-Account Support

```mermaid
graph TD
    User[Alfred User] -->|account_label=personal| T1[GitHub Token<br/>@octocat<br/>OAuth]
    User -->|account_label=work| T2[GitHub Token<br/>@octocat-corp<br/>OAuth]
    User -->|account_label=default| T3[Slack Token<br/>OAuth]

    T1 -->|github_app_config_id| AC1[GitHubAppConfig<br/>label=Personal<br/>client_id=Iv1.abc]
    T2 -->|github_app_config_id| AC2[GitHubAppConfig<br/>label=Work<br/>client_id=Iv1.xyz]

    AC1 --> DB[(github_app_configs)]
    AC2 --> DB
    T1 --> DB2[(user_oauth_tokens<br/>UNIQUE: user_id + provider + account_label)]
    T2 --> DB2
    T3 --> DB2
```

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/github/app-configs` | List user's registered GitHub App configs |
| POST | `/api/github/app-configs` | Register a new per-user GitHub App config |
| DELETE | `/api/github/app-configs/{config_id}` | Delete a GitHub App config |
| GET | `/api/github/oauth/url?account_label=...&app_config_id=...` | Generate OAuth authorization URL |
| GET | `/api/github/oauth/callback?code=...&state=...` | OAuth callback (redirects to frontend) |
| GET | `/api/github/connections` | List all GitHub connections for current user |
| POST | `/api/github/connections/pat` | Add a personal access token |
| DELETE | `/api/github/connections/{connection_id}` | Remove a connection |

## Components

### Backend
- **GitHubService** (`app/services/github.py`): OAuth flow, PAT validation, token refresh, GitHub API calls, app config CRUD
- **GitHubAppConfigRepository** (`app/db/repositories/github_app_config.py`): CRUD for per-user app configs
- **GitHubAppConfig model** (`app/db/models/github_app_config.py`): Per-user GitHub App credentials (encrypted)
- **GitHub API endpoints** (`app/api/github.py`): REST endpoints for frontend
- **GitHub schemas** (`app/schemas/github.py`): Pydantic request/response models
- **OAuthStateStore** (`app/core/oauth_state.py`): Shared CSRF state management (stores app_config_id)

### Frontend
- **IntegrationsPage** (`pages/IntegrationsPage.tsx`): Hub page for all integrations
- **GitHubConnectionCard** (`components/settings/GitHubConnectionCard.tsx`): App config list + connection list
- **ConnectGitHubModal** (`components/settings/ConnectGitHubModal.tsx`): OAuth connect with account label + app config selection
- **AddGitHubAppModal** (`components/settings/AddGitHubAppModal.tsx`): Register a per-user GitHub App
- **AddPATModal** (`components/settings/AddPATModal.tsx`): Dialog for manual PAT entry
- **useGitHub hook** (`hooks/useGitHub.ts`): React Query hooks for GitHub API (connections, app configs, OAuth)

## Token Refresh

GitHub App OAuth tokens expire in 8 hours. The `GitHubService.get_valid_token()` method auto-refreshes expired tokens using the credentials from the token's linked app config (or global fallback):

```mermaid
flowchart TD
    A[get_valid_token] --> B{Token exists?}
    B -->|No| C[Return None]
    B -->|Yes| D{Expired?}
    D -->|No| E[Return decrypted token]
    D -->|Yes| F{Is PAT?}
    F -->|Yes| E
    F -->|No| G{Has refresh_token?}
    G -->|No| C
    G -->|Yes| H[Resolve credentials via<br/>token.github_app_config_id]
    H --> I[POST /login/oauth/access_token<br/>grant_type=refresh_token]
    I --> J[Store new tokens encrypted]
    J --> E
```
