"""Slack integration endpoints."""

import asyncio
import json
import logging
from typing import Any

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request, status
from pydantic import BaseModel

from app.agents import AlfredAgent
from app.api.deps import DbSession, get_db
from app.core.redis import get_redis
from app.db.repositories import SessionRepository, UserRepository
from app.services.linking import get_linking_service
from app.services.slack import get_slack_service

# Event deduplication TTL (5 minutes)
EVENT_DEDUP_TTL = 300

logger = logging.getLogger(__name__)

router = APIRouter()


class SlackChallenge(BaseModel):
    """Schema for Slack URL verification challenge."""

    challenge: str


class SlackEventWrapper(BaseModel):
    """Wrapper for Slack event payload."""

    type: str
    challenge: str | None = None
    event: dict[str, Any] | None = None


class SlackCommandPayload(BaseModel):
    """Schema for Slack slash command."""

    command: str
    user_id: str
    channel_id: str
    text: str | None = None
    response_url: str | None = None


async def verify_slack_request(request: Request) -> bytes:
    """Verify Slack request signature and return body."""
    body = await request.body()

    # Get signature headers
    timestamp = request.headers.get("X-Slack-Request-Timestamp", "")
    signature = request.headers.get("X-Slack-Signature", "")

    slack_service = get_slack_service()
    if not await slack_service.verify_signature(body, timestamp, signature):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Slack signature",
        )

    return body


@router.post("/events")
async def handle_slack_events(
    request: Request,
    background_tasks: BackgroundTasks,
) -> dict[str, Any]:
    """
    Handle Slack Events API webhooks.

    Handles:
    - url_verification: Challenge response for app setup
    - event_callback: Message events from Slack

    Events are processed in the background to respond quickly to Slack.
    """
    body = await request.body()

    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid JSON payload",
        )

    # Handle URL verification (doesn't require signature verification)
    if payload.get("type") == "url_verification":
        return {"challenge": payload.get("challenge", "")}

    # For all other events, verify signature
    timestamp = request.headers.get("X-Slack-Request-Timestamp", "")
    signature = request.headers.get("X-Slack-Signature", "")

    slack_service = get_slack_service()
    if not await slack_service.verify_signature(body, timestamp, signature):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Slack signature",
        )

    # Handle event callbacks
    if payload.get("type") == "event_callback":
        event_id = payload.get("event_id")
        event = payload.get("event", {})

        # Check for duplicate event (Slack may retry)
        if event_id:
            redis = await get_redis()
            dedup_key = f"slack_event:{event_id}"

            # Try to set the key - if it already exists, skip this event
            was_set = await redis.set(dedup_key, "1", nx=True, ex=EVENT_DEDUP_TTL)
            if not was_set:
                logger.info(f"Skipping duplicate Slack event: {event_id}")
                return {"ok": True}

        # Process in background to respond quickly to Slack
        background_tasks.add_task(process_message_event_background, event)

    return {"ok": True}


async def process_message_event_background(event: dict[str, Any]) -> None:
    """Process Slack message event in background with its own DB session."""
    # Get a fresh database session for background processing
    async for db in get_db():
        try:
            await handle_message_event(event, db)
        except Exception as e:
            logger.error(f"Error in background Slack event processing: {e}")


async def handle_message_event(event: dict[str, Any], db) -> None:
    """
    Handle Slack message events.

    Process incoming messages from DMs or mentions.
    """
    event_type = event.get("type")

    # Only handle message events (not bot messages, message changes, etc.)
    if event_type not in ("message", "app_mention"):
        return

    # Ignore bot messages to prevent loops
    if event.get("bot_id") or event.get("subtype") == "bot_message":
        return

    slack_user_id = event.get("user")
    channel_id = event.get("channel")
    text = event.get("text", "").strip()
    thread_ts = event.get("thread_ts") or event.get("ts")

    if not slack_user_id or not channel_id or not text:
        return

    # Remove bot mention from text if present
    text = _strip_bot_mention(text)

    if not text:
        return

    slack_service = get_slack_service()
    user_repo = UserRepository(db)
    session_repo = SessionRepository(db)

    # Look up user by Slack ID
    user = await user_repo.get_by_slack_id(slack_user_id)

    if not user:
        # User not linked - send linking instructions
        await slack_service.send_message(
            channel=channel_id,
            text=(
                "I don't recognize your Slack account. "
                "Please link it first:\n\n"
                "1. Type `/alfred-link` to get a linking code\n"
                "2. Go to Alfred webapp Settings\n"
                "3. Enter the code to link your accounts"
            ),
            thread_ts=thread_ts,
        )
        return

    # Find or create session for this thread
    session = await session_repo.get_by_slack_thread(channel_id, thread_ts)

    if not session:
        # Create new Slack session
        session = await session_repo.create_session(
            user_id=user.id,
            title=f"Slack conversation",
            source="slack",
            slack_channel_id=channel_id,
            slack_thread_ts=thread_ts,
        )

    # Process message through Alfred agent
    try:
        agent = AlfredAgent(db=db)
        response = await agent.run(
            session_id=session.id,
            user_id=user.id,
            message=text,
        )

        # Send response back to Slack
        await slack_service.send_message(
            channel=channel_id,
            text=response,
            thread_ts=thread_ts,
        )
    except Exception as e:
        logger.error(f"Error processing Slack message: {e}")
        await slack_service.send_message(
            channel=channel_id,
            text="I'm sorry, I encountered an error processing your message. Please try again.",
            thread_ts=thread_ts,
        )


def _strip_bot_mention(text: str) -> str:
    """Remove bot mention from message text."""
    import re

    # Remove <@BOT_ID> mentions
    return re.sub(r"<@[A-Z0-9]+>\s*", "", text).strip()


@router.post("/commands")
async def handle_slack_commands(request: Request) -> dict[str, Any]:
    """
    Handle Slack slash commands.

    Supported commands:
    - /alfred-link: Generate a linking code
    """
    # Parse form data (Slack sends commands as form-encoded)
    body = await request.body()

    # Verify signature
    timestamp = request.headers.get("X-Slack-Request-Timestamp", "")
    signature = request.headers.get("X-Slack-Signature", "")

    slack_service = get_slack_service()
    if not await slack_service.verify_signature(body, timestamp, signature):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Slack signature",
        )

    # Parse form data
    form_data = await request.form()
    command = form_data.get("command", "")
    slack_user_id = form_data.get("user_id", "")

    if command == "/alfred-link":
        return await handle_link_command(slack_user_id)

    return {
        "response_type": "ephemeral",
        "text": f"Unknown command: {command}",
    }


async def handle_link_command(slack_user_id: str) -> dict[str, Any]:
    """
    Handle /alfred-link command.

    Generates a one-time linking code for the user.
    """
    if not slack_user_id:
        return {
            "response_type": "ephemeral",
            "text": "Error: Could not identify your Slack user ID.",
        }

    linking_service = get_linking_service()
    code = await linking_service.create_code(slack_user_id)

    return {
        "response_type": "ephemeral",
        "text": (
            f"Your linking code is: *{code}*\n\n"
            "This code expires in 10 minutes.\n\n"
            "To complete linking:\n"
            "1. Go to Alfred webapp\n"
            "2. Navigate to Settings\n"
            "3. Click 'Link Slack Account'\n"
            "4. Enter the code above"
        ),
    }
