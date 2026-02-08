"""Authentication endpoints for user registration and login."""

from fastapi import APIRouter, HTTPException, status

from app.api.deps import CurrentUser, DbSession
from app.core.security import create_access_token, hash_password, verify_password
from app.db.repositories import UserRepository
from app.schemas.auth import (
    SlackLinkRequest,
    SlackStatusResponse,
    TokenResponse,
    UserLogin,
    UserRegister,
    UserResponse,
)
from app.services.linking import get_linking_service

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
