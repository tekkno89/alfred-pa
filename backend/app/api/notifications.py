"""Notification SSE endpoint."""

import asyncio
import logging

from fastapi import APIRouter, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select

from app.api.deps import OptionalUser
from app.core.security import decode_access_token
from app.db.models import User
from app.db.session import async_session_maker
from app.services.notifications import NotificationService, format_sse_event

logger = logging.getLogger(__name__)

router = APIRouter()


async def _resolve_user_from_token(token: str) -> User | None:
    """Resolve a User from a JWT token string (for query-param auth on SSE)."""
    payload = decode_access_token(token)
    if not payload:
        return None
    user_id = payload.get("sub")
    if not user_id:
        return None
    async with async_session_maker() as db:
        result = await db.execute(select(User).where(User.id == user_id))
        return result.scalar_one_or_none()


@router.get("/subscribe")
async def subscribe_notifications(
    current_user: OptionalUser,
    token: str | None = Query(None),
) -> StreamingResponse:
    """
    Subscribe to real-time notifications via Server-Sent Events.

    Supports both Bearer header auth and ?token= query param auth.
    Query param auth is needed for native EventSource which cannot set headers.
    """
    # Resolve user: prefer injected user, fall back to query param
    user = current_user
    if user is None and token:
        user = await _resolve_user_from_token(token)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )

    user_id = user.id

    async def event_generator():
        queue = await NotificationService.register_sse_client(user_id)
        try:
            # Send initial connection event
            yield await format_sse_event({
                "type": "connected",
                "message": "Connected to notification stream",
            })

            while True:
                try:
                    # Wait for events with timeout for keepalive
                    event = await asyncio.wait_for(queue.get(), timeout=30.0)
                    yield await format_sse_event(event)
                except asyncio.TimeoutError:
                    # Send keepalive
                    yield ": keepalive\n\n"
        except asyncio.CancelledError:
            pass
        finally:
            await NotificationService.unregister_sse_client(user_id, queue)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable nginx buffering
        },
    )
