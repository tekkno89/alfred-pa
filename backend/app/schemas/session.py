from datetime import datetime

from pydantic import BaseModel, ConfigDict


class SessionCreate(BaseModel):
    """Schema for creating a new session."""

    title: str | None = None


class SessionUpdate(BaseModel):
    """Schema for updating a session."""

    title: str | None = None
    is_starred: bool | None = None


class SessionResponse(BaseModel):
    """Schema for session response."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    title: str | None
    source: str
    slack_channel_id: str | None
    slack_thread_ts: str | None
    is_starred: bool
    session_type: str | None
    created_at: datetime
    updated_at: datetime


class ContextUsage(BaseModel):
    """Context window usage metrics."""

    tokens_used: int
    token_limit: int
    percentage: float
    model: str


class SessionWithMessages(SessionResponse):
    """Schema for session with messages included."""

    messages: list["MessageResponse"] = []
    context_usage: ContextUsage | None = None
    conversation_summary: str | None = None


class SessionList(BaseModel):
    """Schema for paginated session list."""

    items: list[SessionResponse]
    total: int
    page: int
    size: int


class DeleteResponse(BaseModel):
    """Schema for delete operation response."""

    success: bool


# Import at the bottom to avoid circular import
from app.schemas.message import MessageResponse  # noqa: E402

SessionWithMessages.model_rebuild()
