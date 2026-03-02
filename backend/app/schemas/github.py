"""GitHub integration schemas for request/response validation."""

from datetime import datetime

from pydantic import BaseModel, Field


class GitHubOAuthUrlResponse(BaseModel):
    """Response containing the GitHub OAuth URL."""

    url: str


class GitHubPATRequest(BaseModel):
    """Request to add a personal access token."""

    token: str = Field(..., min_length=1)
    account_label: str = Field(default="default", min_length=1, max_length=100)


class GitHubConnectionResponse(BaseModel):
    """Response for a single GitHub connection."""

    model_config = {"from_attributes": True}

    id: str
    provider: str
    account_label: str
    external_account_id: str | None = None
    token_type: str
    scope: str | None = None
    expires_at: datetime | None = None
    created_at: datetime
    app_config_id: str | None = None
    app_config_label: str | None = None


class GitHubConnectionListResponse(BaseModel):
    """Response listing all GitHub connections."""

    connections: list[GitHubConnectionResponse]


# --- App Config Schemas ---


class GitHubAppConfigCreateRequest(BaseModel):
    """Request to register a per-user GitHub App."""

    label: str = Field(..., min_length=1, max_length=100)
    client_id: str = Field(..., min_length=1, max_length=255)
    client_secret: str = Field(..., min_length=1)
    github_app_id: str | None = Field(default=None, max_length=100)


class GitHubAppConfigResponse(BaseModel):
    """Response for a single GitHub App config (no secrets)."""

    model_config = {"from_attributes": True}

    id: str
    label: str
    client_id: str
    github_app_id: str | None = None
    created_at: datetime


class GitHubAppConfigListResponse(BaseModel):
    """Response listing all GitHub App configs."""

    configs: list[GitHubAppConfigResponse]
