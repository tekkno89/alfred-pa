"""Note schemas for API request/response."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class NoteCreate(BaseModel):
    """Schema for creating a new note."""

    title: str = ""
    body: str = ""
    is_favorited: bool = False
    tags: list[str] = []


class NoteUpdate(BaseModel):
    """Schema for updating a note."""

    title: str | None = None
    body: str | None = None
    is_favorited: bool | None = None
    tags: list[str] | None = None


class NoteResponse(BaseModel):
    """Schema for note response."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    title: str
    body: str
    is_favorited: bool
    is_archived: bool
    tags: list[str]
    created_at: datetime
    updated_at: datetime


class NoteList(BaseModel):
    """Schema for paginated note list."""

    items: list[NoteResponse]
    total: int
    page: int
    size: int
