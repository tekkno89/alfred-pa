from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class UserRepoCreate(BaseModel):
    owner: str = Field(..., min_length=1, max_length=255)
    repo_name: str = Field(..., min_length=1, max_length=255)
    alias: str | None = Field(None, max_length=100)
    github_account_label: str | None = Field(None, max_length=100)


class UserRepoUpdate(BaseModel):
    alias: str | None = None
    github_account_label: str | None = None


class UserRepoResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    owner: str
    repo_name: str
    full_name: str
    alias: str | None
    github_account_label: str | None
    created_at: datetime
    updated_at: datetime


class UserRepoList(BaseModel):
    items: list[UserRepoResponse]
    total: int
