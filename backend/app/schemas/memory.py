"""Memory schemas for API request/response."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict


class MemoryCreate(BaseModel):
    """Schema for creating a new memory."""

    type: Literal["preference", "knowledge", "summary"]
    content: str


class MemoryUpdate(BaseModel):
    """Schema for updating a memory."""

    content: str


class MemoryResponse(BaseModel):
    """Schema for memory response."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    type: str
    content: str
    source_session_id: str | None
    created_at: datetime
    updated_at: datetime


class MemoryList(BaseModel):
    """Schema for paginated memory list."""

    items: list[MemoryResponse]
    total: int
    page: int
    size: int
