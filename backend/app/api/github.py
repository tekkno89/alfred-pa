"""GitHub integration API endpoints."""

from fastapi import APIRouter, HTTPException, Query, status
from fastapi.responses import RedirectResponse

from app.api.deps import CurrentUser, DbSession
from app.core.config import get_settings
from app.core.oauth_state import consume_oauth_state
from app.db.repositories import GitHubAppConfigRepository, OAuthTokenRepository
from app.schemas.github import (
    GitHubAppConfigCreateRequest,
    GitHubAppConfigListResponse,
    GitHubAppConfigResponse,
    GitHubConnectionListResponse,
    GitHubConnectionResponse,
    GitHubOAuthUrlResponse,
    GitHubPATRequest,
)
from app.services.github import GitHubService

router = APIRouter()


# --- App Config Endpoints ---


@router.get("/app-configs", response_model=GitHubAppConfigListResponse)
async def list_app_configs(
    current_user: CurrentUser,
    db: DbSession,
) -> GitHubAppConfigListResponse:
    """List all registered GitHub App configs for the current user."""
    github_service = GitHubService(db)
    configs = await github_service.get_app_configs(current_user.id)
    return GitHubAppConfigListResponse(
        configs=[
            GitHubAppConfigResponse(
                id=c.id,
                label=c.label,
                client_id=c.client_id,
                github_app_id=c.github_app_id,
                created_at=c.created_at,
            )
            for c in configs
        ]
    )


@router.post(
    "/app-configs",
    response_model=GitHubAppConfigResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_app_config(
    data: GitHubAppConfigCreateRequest,
    current_user: CurrentUser,
    db: DbSession,
) -> GitHubAppConfigResponse:
    """Register a new per-user GitHub App configuration."""
    github_service = GitHubService(db)

    try:
        config = await github_service.create_app_config(
            user_id=current_user.id,
            label=data.label,
            client_id=data.client_id,
            client_secret=data.client_secret,
            github_app_id=data.github_app_id,
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )

    return GitHubAppConfigResponse(
        id=config.id,
        label=config.label,
        client_id=config.client_id,
        github_app_id=config.github_app_id,
        created_at=config.created_at,
    )


@router.delete(
    "/app-configs/{config_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_app_config(
    config_id: str,
    current_user: CurrentUser,
    db: DbSession,
) -> None:
    """Delete a GitHub App configuration."""
    github_service = GitHubService(db)
    deleted = await github_service.delete_app_config(config_id, current_user.id)

    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="App config not found",
        )


# --- OAuth Endpoints ---


@router.get("/oauth/url", response_model=GitHubOAuthUrlResponse)
async def get_github_oauth_url(
    current_user: CurrentUser,
    db: DbSession,
    account_label: str = Query(default="default"),
    app_config_id: str | None = Query(default=None),
) -> GitHubOAuthUrlResponse:
    """Generate GitHub OAuth authorization URL."""
    github_service = GitHubService(db)

    try:
        url = await github_service.get_oauth_url(
            current_user.id, account_label, app_config_id=app_config_id
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )

    return GitHubOAuthUrlResponse(url=url)


@router.get("/oauth/callback")
async def github_oauth_callback(
    code: str = Query(...),
    state: str = Query(...),
    db: DbSession = None,
) -> RedirectResponse:
    """Handle GitHub OAuth callback. Exchanges code for token and redirects to frontend."""
    settings = get_settings()

    # Validate state
    state_data = consume_oauth_state(state)
    if not state_data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired OAuth state",
        )

    user_id = state_data["user_id"]
    account_label = state_data.get("account_label", "default")
    app_config_id = state_data.get("app_config_id")

    github_service = GitHubService(db)

    try:
        token_data = await github_service.exchange_code(
            code, app_config_id=app_config_id
        )
        await github_service.store_oauth_token(
            user_id=user_id,
            token_data=token_data,
            account_label=account_label,
            app_config_id=app_config_id,
        )
    except ValueError as e:
        redirect_url = f"{settings.frontend_url}/settings/integrations?github_oauth=error&message={str(e)}"
        return RedirectResponse(url=redirect_url)

    redirect_url = f"{settings.frontend_url}/settings/integrations?github_oauth=success"
    return RedirectResponse(url=redirect_url)


# --- Connection Endpoints ---


@router.get("/connections", response_model=GitHubConnectionListResponse)
async def list_github_connections(
    current_user: CurrentUser,
    db: DbSession,
) -> GitHubConnectionListResponse:
    """List all GitHub connections for the current user."""
    token_repo = OAuthTokenRepository(db)
    tokens = await token_repo.get_all_by_user_and_provider(
        current_user.id, "github"
    )

    connections = []
    for t in tokens:
        # Eagerly load the app config label if linked
        app_config_label = None
        if t.github_app_config_id:
            config_repo = GitHubAppConfigRepository(db)
            config = await config_repo.get(t.github_app_config_id)
            if config:
                app_config_label = config.label

        connections.append(
            GitHubConnectionResponse(
                id=t.id,
                provider=t.provider,
                account_label=t.account_label,
                external_account_id=t.external_account_id,
                token_type=t.token_type,
                scope=t.scope,
                expires_at=t.expires_at,
                created_at=t.created_at,
                app_config_id=t.github_app_config_id,
                app_config_label=app_config_label,
            )
        )

    return GitHubConnectionListResponse(connections=connections)


@router.post(
    "/connections/pat",
    response_model=GitHubConnectionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def add_github_pat(
    data: GitHubPATRequest,
    current_user: CurrentUser,
    db: DbSession,
) -> GitHubConnectionResponse:
    """Add a GitHub Personal Access Token."""
    github_service = GitHubService(db)

    try:
        token = await github_service.store_pat(
            user_id=current_user.id,
            pat=data.token,
            account_label=data.account_label,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid token: {e}",
        )

    return GitHubConnectionResponse(
        id=token.id,
        provider=token.provider,
        account_label=token.account_label,
        external_account_id=token.external_account_id,
        token_type=token.token_type,
        scope=token.scope,
        expires_at=token.expires_at,
        created_at=token.created_at,
    )


@router.delete(
    "/connections/{connection_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_github_connection(
    connection_id: str,
    current_user: CurrentUser,
    db: DbSession,
) -> None:
    """Remove a GitHub connection."""
    github_service = GitHubService(db)
    deleted = await github_service.delete_connection(connection_id, current_user.id)

    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Connection not found",
        )
