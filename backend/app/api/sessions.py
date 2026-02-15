import json
import logging
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
from app.services.slack import get_slack_service

logger = logging.getLogger(__name__)


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
    starred: Annotated[bool | None, Query()] = None,
) -> SessionList:
    """List sessions for the current user."""
    repo = SessionRepository(db)
    skip = (page - 1) * size

    sessions = await repo.get_user_sessions(
        user_id=user.id,
        skip=skip,
        limit=size,
        starred=starred,
    )
    total = await repo.count_user_sessions(user_id=user.id, starred=starred)

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
    if session_data.is_starred is not None:
        updates["is_starred"] = session_data.is_starred

    if updates:
        session = await repo.update(session, **updates)

    return SessionResponse.model_validate(session)


@router.patch("/{session_id}/star", response_model=SessionResponse)
async def toggle_session_star(
    session_id: str,
    db: DbSession,
    user: CurrentUser,
) -> SessionResponse:
    """Toggle the starred status of a session."""
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

    session = await repo.update(session, is_starred=not session.is_starred)
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

    If the session originated from Slack, the response will also be
    posted back to the Slack thread (cross-sync).
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

    # Capture Slack metadata for cross-sync
    slack_channel_id = session.slack_channel_id
    slack_thread_ts = session.slack_thread_ts
    user_email = user.email

    # Sync user message to Slack before processing (if Slack session)
    if slack_channel_id and slack_thread_ts:
        await _sync_user_message_to_slack(
            slack_channel_id, slack_thread_ts, message_data.content, user_email
        )

    async def event_stream():
        agent = AlfredAgent(db=db)
        full_response: list[str] = []

        try:
            async for event in agent.stream(
                session_id=session_id,
                user_id=user.id,
                message=message_data.content,
            ):
                if event["type"] == "token":
                    full_response.append(event["content"])
                    sse = StreamEvent(type="token", content=event["content"])
                elif event["type"] == "tool_use":
                    sse = StreamEvent(type="tool_use", tool_name=event["tool_name"])
                else:
                    continue
                yield f"data: {sse.model_dump_json()}\n\n"

            # Send done event
            done_event = StreamEvent(type="done")
            yield f"data: {done_event.model_dump_json()}\n\n"

            # Cross-sync AI response to Slack if session has Slack metadata
            if slack_channel_id and slack_thread_ts:
                response_text = "".join(full_response)
                await _sync_to_slack(slack_channel_id, slack_thread_ts, response_text)

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


async def _sync_user_message_to_slack(
    channel_id: str, thread_ts: str, message: str, user_email: str
) -> None:
    """
    Post user's message to Slack thread with attribution.

    Shows the message as coming from the webapp with the user's identity.
    Uses blockquote formatting for visual distinction.
    """
    try:
        slack_service = get_slack_service()
        # Format with blockquote for visual distinction
        username = user_email.split("@")[0]  # Use part before @ as display name
        # Indent message lines with > for blockquote effect
        quoted_message = "\n".join(f"> {line}" for line in message.split("\n"))
        formatted_message = f":speech_balloon: *{username}* _(via webapp)_:\n{quoted_message}"
        await slack_service.send_message(
            channel=channel_id,
            text=formatted_message,
            thread_ts=thread_ts,
        )
    except Exception as e:
        logger.error(f"Failed to sync user message to Slack: {e}")


async def _sync_to_slack(channel_id: str, thread_ts: str, message: str) -> None:
    """
    Post a message to Slack thread (cross-sync).

    Errors are logged but not raised to avoid failing the main request.
    """
    try:
        slack_service = get_slack_service()
        await slack_service.send_message(
            channel=channel_id,
            text=message,
            thread_ts=thread_ts,
        )
    except Exception as e:
        logger.error(f"Failed to sync message to Slack: {e}")
