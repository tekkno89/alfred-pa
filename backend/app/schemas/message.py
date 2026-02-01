from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict


class MessageCreate(BaseModel):
    """Schema for creating a new message."""

    content: str


class MessageResponse(BaseModel):
    """Schema for message response."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    session_id: str
    role: str
    content: str
    metadata_: dict[str, Any] | None = None
    created_at: datetime


class MessageList(BaseModel):
    """Schema for paginated message list."""

    items: list[MessageResponse]
    total: int


class StreamEvent(BaseModel):
    """Schema for streaming response events."""

    type: Literal["token", "done", "error"]
    content: str | None = None
    message_id: str | None = None
