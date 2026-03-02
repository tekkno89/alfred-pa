"""Todo schemas for API request/response."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class TodoCreate(BaseModel):
    """Schema for creating a new todo."""

    title: str = Field(..., min_length=1, max_length=500)
    description: str | None = None
    priority: int = Field(default=2, ge=0, le=3)
    due_at: datetime | None = None
    is_starred: bool = False
    tags: list[str] = []
    recurrence_rule: str | None = None


class TodoUpdate(BaseModel):
    """Schema for updating a todo."""

    title: str | None = None
    description: str | None = None
    priority: int | None = Field(default=None, ge=0, le=3)
    due_at: datetime | None = None
    is_starred: bool | None = None
    tags: list[str] | None = None
    recurrence_rule: str | None = None
    status: str | None = None


class TodoResponse(BaseModel):
    """Schema for todo response."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    title: str
    description: str | None
    priority: int
    status: str
    due_at: datetime | None
    completed_at: datetime | None
    is_starred: bool
    tags: list[str]
    recurrence_rule: str | None
    recurrence_parent_id: str | None
    created_at: datetime
    updated_at: datetime


class TodoList(BaseModel):
    """Schema for paginated todo list."""

    items: list[TodoResponse]
    total: int
    page: int
    size: int


class TodoSummary(BaseModel):
    """Schema for todo summary counts (dashboard card)."""

    overdue: int
    due_today: int
    due_this_week: int
    total_open: int
