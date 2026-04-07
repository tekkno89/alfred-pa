"""Coding job schemas for API request/response."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class CodingJobResponse(BaseModel):
    """Schema for coding job response."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    user_id: str
    session_id: str
    status: str
    mode: str
    repo_full_name: str
    branch_name: str | None
    pr_url: str | None
    pr_number: int | None
    task_description: str
    plan_content: str | None
    review_content: str | None
    revision_of_job_id: str | None
    error_details: str | None
    github_account_label: str | None
    slack_channel_id: str | None
    slack_thread_ts: str | None
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime
    updated_at: datetime


class CodingJobList(BaseModel):
    """Schema for paginated coding job list."""

    items: list[CodingJobResponse]
    total: int
    page: int
    size: int


class CodingJobRevisionRequest(BaseModel):
    """Schema for requesting a revision to an existing coding job."""

    description: str = Field(..., min_length=1, max_length=5000)


class CodingJobCallbackRequest(BaseModel):
    """Schema for container completion callback."""

    job_id: str
    success: bool
    exit_code: int = 0
    output_files: dict[str, str] = Field(default_factory=dict)
    error: str | None = None
    logs: str | None = None
    mode: str | None = None
