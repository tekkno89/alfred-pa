"""Authentication endpoints for user registration and login."""

import secrets
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, HTTPException, Query, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

from app.api.deps import CurrentUser, DbSession
from app.core.config import get_settings
from app.core.security import create_access_token, hash_password, verify_password
from app.db.repositories import UserRepository, OAuthTokenRepository
from app.schemas.auth import (
    SlackLinkRequest,
    SlackStatusResponse,
    SlackOAuthStatusResponse,
    TokenResponse,
    UserLogin,
    UserRegister,
    UserResponse,
)
from app.services.linking import get_linking_service
from app.services.slack_user import SlackUserService

router = APIRouter()


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(data: UserRegister, db: DbSession) -> TokenResponse:
    """
    Register a new user with email and password.

    Returns a JWT access token on successful registration.
    """
    user_repo = UserRepository(db)

    # Check if email already exists
    existing_user = await user_repo.get_by_email(data.email)
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered",
        )

    # Create user with hashed password
    password_hash = hash_password(data.password)
    user = await user_repo.create_user(email=data.email, password_hash=password_hash)

    # Generate access token
    access_token = create_access_token(user.id)
    return TokenResponse(access_token=access_token)


@router.post("/login", response_model=TokenResponse)
async def login(data: UserLogin, db: DbSession) -> TokenResponse:
    """
    Authenticate user with email and password.

    Returns a JWT access token on successful login.
    """
    user_repo = UserRepository(db)

    # Find user by email
    user = await user_repo.get_by_email(data.email)
    if not user or not user.password_hash:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    # Verify password
    if not verify_password(data.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    # Generate access token
    access_token = create_access_token(user.id)
    return TokenResponse(access_token=access_token)


@router.get("/me", response_model=UserResponse)
async def get_current_user_profile(current_user: CurrentUser) -> UserResponse:
    """
    Get the current authenticated user's profile.

    Requires a valid JWT token in the Authorization header.
    """
    return UserResponse(
        id=current_user.id,
        email=current_user.email,
        slack_user_id=current_user.slack_user_id,
        created_at=current_user.created_at,
    )


@router.get("/slack-status", response_model=SlackStatusResponse)
async def get_slack_status(current_user: CurrentUser) -> SlackStatusResponse:
    """
    Check if current user has linked their Slack account.

    Returns the linked status and Slack user ID if linked.
    """
    return SlackStatusResponse(
        linked=current_user.slack_user_id is not None,
        slack_user_id=current_user.slack_user_id,
    )


@router.post("/link-slack", response_model=SlackStatusResponse)
async def link_slack_account(
    data: SlackLinkRequest,
    current_user: CurrentUser,
    db: DbSession,
) -> SlackStatusResponse:
    """
    Link a Slack account using a linking code.

    The code is generated via the /alfred-link Slack command.
    """
    linking_service = get_linking_service()

    # Validate the code and get the Slack user ID
    slack_user_id = await linking_service.validate_code(data.code)

    if not slack_user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired linking code",
        )

    # Link the Slack account to the user
    user_repo = UserRepository(db)
    try:
        await user_repo.link_slack(current_user.id, slack_user_id)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )

    return SlackStatusResponse(
        linked=True,
        slack_user_id=slack_user_id,
    )


@router.post("/unlink-slack", response_model=SlackStatusResponse)
async def unlink_slack_account(
    current_user: CurrentUser,
    db: DbSession,
) -> SlackStatusResponse:
    """
    Unlink the current user's Slack account.
    """
    if not current_user.slack_user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No Slack account linked",
        )

    user_repo = UserRepository(db)
    await user_repo.unlink_slack(current_user.id)

    return SlackStatusResponse(linked=False)


# Slack OAuth endpoints for user token (status/presence control)
# Note: These are separate from the Slack linking flow above.
# Linking connects a Slack user ID to an Alfred account.
# OAuth grants Alfred permission to act on behalf of the user (set status, etc.)

# Store OAuth state tokens in memory (in production, use Redis)
_oauth_states: dict[str, str] = {}


class SlackOAuthUrlResponse(BaseModel):
    """Response containing the Slack OAuth URL."""
    url: str


@router.get("/slack/oauth/url", response_model=SlackOAuthUrlResponse)
async def get_slack_oauth_url(current_user: CurrentUser) -> SlackOAuthUrlResponse:
    """
    Get the Slack OAuth authorization URL.

    Frontend should call this, then redirect to the returned URL.
    """
    settings = get_settings()

    if not settings.slack_client_id:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Slack OAuth not configured",
        )

    # Generate state token for CSRF protection
    state = secrets.token_urlsafe(32)
    _oauth_states[state] = current_user.id

    # Slack OAuth scopes for user token
    # user_scope is for user token permissions, scope is for bot token
    user_scopes = "users.profile:read,users.profile:write"

    params = {
        "client_id": settings.slack_client_id,
        "user_scope": user_scopes,  # Request user token scopes only
        "redirect_uri": settings.slack_oauth_redirect_uri,
        "state": state,
    }

    auth_url = f"https://slack.com/oauth/v2/authorize?{urlencode(params)}"
    return SlackOAuthUrlResponse(url=auth_url)


@router.get("/slack/oauth/callback")
async def slack_oauth_callback(
    code: str = Query(...),
    state: str = Query(...),
    db: DbSession = None,
) -> RedirectResponse:
    """
    Handle Slack OAuth callback.

    Exchanges the authorization code for an access token.
    """
    settings = get_settings()

    # Validate state
    user_id = _oauth_states.pop(state, None)
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired OAuth state",
        )

    # Exchange code for token
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "https://slack.com/api/oauth.v2.access",
            data={
                "client_id": settings.slack_client_id,
                "client_secret": settings.slack_client_secret,
                "code": code,
                "redirect_uri": settings.slack_oauth_redirect_uri,
            },
        )

    data = response.json()

    if not data.get("ok"):
        error = data.get("error", "Unknown error")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Slack OAuth failed: {error}",
        )

    # Extract user token (authed_user contains user-scoped token)
    authed_user = data.get("authed_user", {})
    access_token = authed_user.get("access_token")
    scope = authed_user.get("scope")

    if not access_token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No user access token received",
        )

    # Store the token
    slack_user_service = SlackUserService(db)
    await slack_user_service.store_token(
        user_id=user_id,
        access_token=access_token,
        scope=scope,
    )

    # Redirect back to frontend settings page
    redirect_url = f"{settings.frontend_url}/settings?oauth=success"
    return RedirectResponse(url=redirect_url)


@router.get("/slack/oauth/status", response_model=SlackOAuthStatusResponse)
async def get_slack_oauth_status(
    current_user: CurrentUser,
    db: DbSession,
) -> SlackOAuthStatusResponse:
    """
    Check if current user has connected Slack OAuth (for status control).
    """
    token_repo = OAuthTokenRepository(db)
    token = await token_repo.get_by_user_and_provider(current_user.id, "slack")

    return SlackOAuthStatusResponse(
        connected=token is not None,
        scope=token.scope if token else None,
    )


@router.delete("/slack/oauth", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_slack_oauth(
    current_user: CurrentUser,
    db: DbSession,
) -> None:
    """
    Revoke Slack OAuth connection.
    """
    slack_user_service = SlackUserService(db)
    deleted = await slack_user_service.revoke_token(current_user.id)

    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No Slack OAuth connection to revoke",
        )
