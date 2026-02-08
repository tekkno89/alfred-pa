"""Authentication schemas for request/response validation."""

from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


class UserRegister(BaseModel):
    """Schema for user registration request."""

    email: EmailStr
    password: str = Field(..., min_length=8)


class UserLogin(BaseModel):
    """Schema for user login request."""

    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    """Schema for authentication token response."""

    access_token: str
    token_type: str = "bearer"


class UserResponse(BaseModel):
    """Schema for user profile response."""

    model_config = {"from_attributes": True}

    id: str
    email: str
    slack_user_id: str | None = None
    created_at: datetime


class SlackLinkRequest(BaseModel):
    """Schema for Slack linking request."""

    code: str = Field(..., min_length=6, max_length=6)


class SlackStatusResponse(BaseModel):
    """Schema for Slack status response."""

    linked: bool
    slack_user_id: str | None = None
