"""Notification SSE endpoint."""

import asyncio
import logging

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from app.api.deps import CurrentUser, DbSession
from app.services.notifications import NotificationService, format_sse_event

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/subscribe")
async def subscribe_notifications(
    current_user: CurrentUser,
    db: DbSession,
) -> StreamingResponse:
    """
    Subscribe to real-time notifications via Server-Sent Events.

    Events include:
    - focus_bypass: When someone triggers the bypass button
    - focus_started: When focus mode is enabled
    - focus_ended: When focus mode is disabled
    - pomodoro_work_started: When a pomodoro work phase starts
    - pomodoro_break_started: When a pomodoro break phase starts
    """

    async def event_generator():
        queue = await NotificationService.register_sse_client(current_user.id)
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
            await NotificationService.unregister_sse_client(current_user.id, queue)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable nginx buffering
        },
    )
