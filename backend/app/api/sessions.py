import json
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents import AlfredAgent
from app.api.deps import CurrentUser, DbSession
from app.db.repositories import MessageRepository, SessionRepository
from app.schemas import (
    DeleteResponse,
    MessageCreate,
    MessageList,
    MessageResponse,
    SessionCreate,
    SessionList,
    SessionResponse,
    SessionUpdate,
    SessionWithMessages,
    StreamEvent,
)


router = APIRouter()


@router.post("", response_model=SessionResponse, status_code=status.HTTP_201_CREATED)
async def create_session(
    session_data: SessionCreate,
    db: DbSession,
    user: CurrentUser,
) -> SessionResponse:
    """Create a new chat session."""
    repo = SessionRepository(db)
    session = await repo.create_session(
        user_id=user.id,
        title=session_data.title,
        source="webapp",
    )
    return SessionResponse.model_validate(session)


@router.get("", response_model=SessionList)
async def list_sessions(
    db: DbSession,
    user: CurrentUser,
    page: Annotated[int, Query(ge=1)] = 1,
    size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> SessionList:
    """List sessions for the current user."""
    repo = SessionRepository(db)
    skip = (page - 1) * size

    sessions = await repo.get_user_sessions(
        user_id=user.id,
        skip=skip,
        limit=size,
    )
    total = await repo.count_user_sessions(user_id=user.id)

    return SessionList(
        items=[SessionResponse.model_validate(s) for s in sessions],
        total=total,
        page=page,
        size=size,
    )


@router.get("/{session_id}", response_model=SessionWithMessages)
async def get_session(
    session_id: str,
    db: DbSession,
    user: CurrentUser,
) -> SessionWithMessages:
    """Get a session with its messages."""
    repo = SessionRepository(db)
    session = await repo.get_with_messages(session_id)

    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found",
        )

    if session.user_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to access this session",
        )

    return SessionWithMessages.model_validate(session)


@router.patch("/{session_id}", response_model=SessionResponse)
async def update_session(
    session_id: str,
    session_data: SessionUpdate,
    db: DbSession,
    user: CurrentUser,
) -> SessionResponse:
    """Update a session (e.g., rename it)."""
    repo = SessionRepository(db)
    session = await repo.get(session_id)

    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found",
        )

    if session.user_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to update this session",
        )

    # Build update dict from provided fields
    updates = {}
    if session_data.title is not None:
        updates["title"] = session_data.title

    if updates:
        session = await repo.update(session, **updates)

    return SessionResponse.model_validate(session)


@router.delete("/{session_id}", response_model=DeleteResponse)
async def delete_session(
    session_id: str,
    db: DbSession,
    user: CurrentUser,
) -> DeleteResponse:
    """Delete a session."""
    repo = SessionRepository(db)
    session = await repo.get(session_id)

    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found",
        )

    if session.user_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to delete this session",
        )

    await repo.delete(session)
    return DeleteResponse(success=True)


@router.get("/{session_id}/messages", response_model=MessageList)
async def get_messages(
    session_id: str,
    db: DbSession,
    user: CurrentUser,
) -> MessageList:
    """Get messages for a session."""
    session_repo = SessionRepository(db)
    session = await session_repo.get(session_id)

    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found",
        )

    if session.user_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to access this session",
        )

    message_repo = MessageRepository(db)
    messages = await message_repo.get_session_messages(session_id)
    total = await message_repo.count_session_messages(session_id)

    return MessageList(
        items=[MessageResponse.model_validate(m) for m in messages],
        total=total,
    )


@router.post("/{session_id}/messages")
async def send_message(
    session_id: str,
    message_data: MessageCreate,
    db: DbSession,
    user: CurrentUser,
) -> StreamingResponse:
    """
    Send a message and get a streaming response.

    Returns Server-Sent Events with the following format:
    - data: {"type": "token", "content": "..."}
    - data: {"type": "done", "message_id": "..."}
    - data: {"type": "error", "content": "..."}
    """
    session_repo = SessionRepository(db)
    session = await session_repo.get(session_id)

    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found",
        )

    if session.user_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to access this session",
        )

    async def event_stream():
        agent = AlfredAgent(db=db)

        try:
            async for token in agent.stream(
                session_id=session_id,
                user_id=user.id,
                message=message_data.content,
            ):
                event = StreamEvent(type="token", content=token)
                yield f"data: {event.model_dump_json()}\n\n"

            # Send done event
            done_event = StreamEvent(type="done")
            yield f"data: {done_event.model_dump_json()}\n\n"

        except Exception as e:
            error_event = StreamEvent(type="error", content=str(e))
            yield f"data: {error_event.model_dump_json()}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
