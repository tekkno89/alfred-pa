import logging
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status
from fastapi.responses import StreamingResponse

from app.agents import AlfredAgent
from app.api.deps import CurrentUser, DbSession
from app.core.config import get_settings
from app.core.summarize import summarize_messages
from app.core.tokens import count_tokens, get_context_limit
from app.db.repositories import MessageRepository, SessionRepository
from app.schemas import (
    ContextUsage,
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


def _compute_context_usage(
    session,
    messages,
) -> ContextUsage:
    """Compute context usage metrics for a session."""
    from app.agents.nodes import SYSTEM_PROMPT

    settings = get_settings()
    model_name = settings.default_llm
    context_limit = get_context_limit(model_name)

    system_tokens = count_tokens(SYSTEM_PROMPT) + 500
    summary_tokens = count_tokens(session.conversation_summary) if session.conversation_summary else 0

    # Only count messages after the summary point
    if session.summary_through_id:
        # Find the summary point and count only messages after it
        found_summary_point = False
        history_tokens = 0
        for msg in messages:
            if found_summary_point:
                history_tokens += count_tokens(msg.content) + 4
            elif msg.id == session.summary_through_id:
                found_summary_point = True
        # If summary point not found (e.g., deleted), count all messages
        if not found_summary_point:
            history_tokens = sum(count_tokens(msg.content) + 4 for msg in messages)
    else:
        history_tokens = sum(count_tokens(msg.content) + 4 for msg in messages)

    total_tokens = system_tokens + summary_tokens + history_tokens
    percentage = round(total_tokens / context_limit * 100, 1) if context_limit > 0 else 0

    return ContextUsage(
        tokens_used=total_tokens,
        token_limit=context_limit,
        percentage=percentage,
        model=model_name,
    )


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

    # Compute context usage for the progress bar on page load
    context_usage = _compute_context_usage(session, session.messages)

    result = SessionWithMessages.model_validate(session)
    result.context_usage = context_usage
    result.conversation_summary = session.conversation_summary
    return result


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
    - data: {"type": "tool_use", "tool_name": "..."}
    - data: {"type": "tool_result", "tool_name": "...", "tool_data": {...}}
    - data: {"type": "done", "message_id": "..."}
    - data: {"type": "context_usage", "tokens_used": ..., "token_limit": ..., "percentage": ..., "model": "..."}
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
        agent = AlfredAgent(db=db, timezone=message_data.timezone)
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
                    sse = StreamEvent(
                        type="tool_use",
                        tool_name=event["tool_name"],
                        tool_args=event.get("tool_args"),
                    )
                elif event["type"] == "tool_result":
                    sse = StreamEvent(
                        type="tool_result",
                        tool_name=event.get("tool_name"),
                        tool_data=event.get("tool_data"),
                    )
                elif event["type"] == "context_usage":
                    sse = StreamEvent(
                        type="context_usage",
                        tokens_used=event.get("tokens_used"),
                        token_limit=event.get("token_limit"),
                        percentage=event.get("percentage"),
                        model=event.get("model"),
                    )
                    yield f"data: {sse.model_dump_json()}\n\n"
                    continue
                else:
                    continue
                yield f"data: {sse.model_dump_json()}\n\n"

            # Send done event
            done_event = StreamEvent(type="done")
            yield f"data: {done_event.model_dump_json()}\n\n"

            # Classify session based on tools used during the stream
            session_repo = SessionRepository(db)
            await session_repo.classify_session(session, agent.tools_used)

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


@router.post("/{session_id}/compact", response_model=ContextUsage)
async def compact_session(
    session_id: str,
    db: DbSession,
    user: CurrentUser,
) -> ContextUsage:
    """
    Manually compact a session by summarizing messages.

    Triggers summarization of all messages after the current summary point,
    updates the session, and returns updated context usage.
    """
    session_repo = SessionRepository(db)
    message_repo = MessageRepository(db)

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

    # Load messages after summary point
    if session.summary_through_id:
        messages = await message_repo.get_messages_after(session_id, session.summary_through_id)
    else:
        messages = await message_repo.get_session_messages(session_id)

    if len(messages) < 2:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Not enough messages to compact",
        )

    # Keep the last 2 messages, summarize the rest
    keep_count = min(2, len(messages))
    to_summarize_msgs = messages[:-keep_count]

    if not to_summarize_msgs:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Not enough messages to compact",
        )

    to_summarize = [
        {"role": msg.role, "content": msg.content}
        for msg in to_summarize_msgs
    ]

    new_summary = await summarize_messages(
        to_summarize,
        existing_summary=session.conversation_summary,
    )

    # Update session with new summary
    last_summarized = to_summarize_msgs[-1]
    await session_repo.update(
        session,
        conversation_summary=new_summary,
        summary_through_id=last_summarized.id,
    )

    # Reload session to recompute context usage
    all_messages = await message_repo.get_session_messages(session_id)
    session = await session_repo.get(session_id)
    return _compute_context_usage(session, all_messages)


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
