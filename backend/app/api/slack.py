"""Slack integration endpoints."""

import asyncio
import hashlib
import hmac
import json
import logging
import time
from typing import Any
from urllib.parse import parse_qs

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request, status
from pydantic import BaseModel

from app.agents import AlfredAgent
from app.api.deps import DbSession, get_db
from app.core.config import get_settings
from app.core.redis import get_redis
from app.db.repositories import SessionRepository, UserRepository
from app.services.focus import FocusModeService
from app.services.linking import get_linking_service
from app.services.notifications import NotificationService
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
        authorizations = payload.get("authorizations", [])

        # Log the incoming event for debugging
        logger.info(f"Slack event received: type={event.get('type')}, "
                    f"channel={event.get('channel')}, "
                    f"user={event.get('user')}, "
                    f"authorizations={authorizations}")

        # Check for duplicate event (Slack may retry)
        if event_id:
            redis = await get_redis()
            dedup_key = f"slack_event:{event_id}"

            # Try to set the key - if it already exists, skip this event
            was_set = await redis.set(dedup_key, "1", nx=True, ex=EVENT_DEDUP_TTL)
            if not was_set:
                logger.info(f"Skipping duplicate Slack event: {event_id}")
                return {"ok": True}

        # Get authorizations (for user-context events)
        authorizations = payload.get("authorizations", [])

        # Process in background to respond quickly to Slack
        background_tasks.add_task(process_message_event_background, event, authorizations)

    return {"ok": True}


async def process_message_event_background(
    event: dict[str, Any],
    authorizations: list[dict[str, Any]] | None = None,
) -> None:
    """Process Slack message event in background with its own DB session."""
    # Get a fresh database session for background processing
    async for db in get_db():
        try:
            await handle_message_event(event, db, authorizations)
        except Exception as e:
            logger.error(f"Error in background Slack event processing: {e}")


async def handle_message_event(
    event: dict[str, Any],
    db,
    authorizations: list[dict[str, Any]] | None = None,
) -> None:
    """
    Handle Slack message events.

    Process incoming messages from DMs or mentions.
    Handles both bot events and user-context events (on behalf of users).
    """
    event_type = event.get("type")

    # Only handle message events (not bot messages, message changes, etc.)
    if event_type not in ("message", "app_mention"):
        return

    # Ignore bot messages to prevent loops
    if event.get("bot_id") or event.get("subtype") == "bot_message":
        return

    sender_slack_id = event.get("user")
    channel_id = event.get("channel")
    original_text = event.get("text", "").strip()
    thread_ts = event.get("thread_ts") or event.get("ts")
    message_ts = event.get("ts")

    if not sender_slack_id or not channel_id or not original_text:
        return

    slack_service = get_slack_service()
    user_repo = UserRepository(db)
    session_repo = SessionRepository(db)
    focus_service = FocusModeService(db)

    # Check if this is a user-context event (event on behalf of a user)
    # For message.im events, this means someone DMed the authorized user
    if authorizations and len(authorizations) > 0:
        auth_entry = authorizations[0]
        authorized_user_slack_id = auth_entry.get("user_id")
        is_bot_authorization = auth_entry.get("is_bot", False)

        # Only process as user-context if the authorized user is a real user
        # (not the bot itself) and is different from the sender
        if (
            authorized_user_slack_id
            and not is_bot_authorization
            and authorized_user_slack_id != sender_slack_id
        ):
            logger.info(
                f"User-context event: {sender_slack_id} -> {authorized_user_slack_id}"
            )

            # Look up the authorized user (recipient of the DM)
            recipient_user = await user_repo.get_by_slack_id(authorized_user_slack_id)

            if recipient_user:
                # Check if recipient is in focus mode
                if await focus_service.is_in_focus_mode(recipient_user.id):
                    # Check if sender is VIP for this user
                    if not await focus_service.is_vip(recipient_user.id, sender_slack_id):
                        # Send auto-reply for the recipient
                        # Use sender_slack_id as channel - this opens a DM between
                        # the bot and sender (bot can't post to user-to-user DMs)
                        custom_message = await focus_service.get_custom_message(
                            recipient_user.id
                        )
                        await send_focus_mode_reply(
                            slack_service,
                            sender_slack_id,  # DM the sender directly
                            None,  # No thread for new DM
                            recipient_user.id,
                            sender_slack_id,
                            custom_message,
                            recipient_slack_id=authorized_user_slack_id,
                        )
                        logger.info(
                            f"Sent focus mode auto-reply for user {recipient_user.id}"
                        )
                        # Don't process further - this was just a focus mode check
                        return

            # For user-context events where recipient isn't in focus mode,
            # we don't need to do anything else (it's their normal DM)
            return

        # User-token event where the sender IS the authorized user —
        # this is the user's own outgoing DM to someone else. Ignore it.
        if not is_bot_authorization:
            return

    # Check if any mentioned users are linked and in focus mode
    # This handles the case where someone mentions a user who is focusing
    mentioned_user_ids = _extract_mentioned_user_ids(original_text)
    logger.info(f"Message from {sender_slack_id}, mentions: {mentioned_user_ids}")
    for mentioned_slack_id in mentioned_user_ids:
        # Skip if the sender mentioned themselves
        if mentioned_slack_id == sender_slack_id:
            continue

        mentioned_user = await user_repo.get_by_slack_id(mentioned_slack_id)
        if not mentioned_user:
            continue

        # Check if the mentioned user is in focus mode
        if await focus_service.is_in_focus_mode(mentioned_user.id):
            # Check if sender is VIP for this user
            if not await focus_service.is_vip(mentioned_user.id, sender_slack_id):
                # Send auto-reply for the mentioned user
                # DM the sender directly (bot may not be in the channel)
                custom_message = await focus_service.get_custom_message(mentioned_user.id)
                await send_focus_mode_reply(
                    slack_service,
                    sender_slack_id,  # DM the sender
                    None,  # No thread for DM
                    mentioned_user.id,
                    sender_slack_id,
                    custom_message,
                    recipient_slack_id=mentioned_slack_id,
                )
                # Continue checking other mentions (don't return)

    # Only continue processing if this is a DM or bot mention
    # For channel messages where only a user was mentioned, we're done
    is_dm_channel = channel_id.startswith("D")
    if not is_dm_channel and event_type != "app_mention":
        # Just a channel message - we've handled any focus mode replies above
        return

    # Remove bot mention from text if present
    text = _strip_bot_mention(original_text)

    if not text:
        return

    # Look up user by Slack ID (the sender)
    # This is for DM conversations with the bot
    user = await user_repo.get_by_slack_id(sender_slack_id)

    if not user:
        # Sender is not linked
        # Only send linking instructions for DM channels (start with 'D')
        # or when the bot was explicitly mentioned (app_mention)
        is_dm_channel = channel_id.startswith("D")
        if is_dm_channel or event_type == "app_mention":
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


async def send_focus_mode_reply(
    slack_service,
    channel_id: str,
    thread_ts: str | None,
    user_id: str,
    sender_slack_id: str,
    custom_message: str | None,
    recipient_slack_id: str | None = None,
) -> None:
    """Send focus mode auto-reply with bypass button."""
    # Create signed payload for bypass button
    settings = get_settings()
    timestamp = str(int(time.time()))
    payload_str = f"{user_id}:{sender_slack_id}:{timestamp}"
    signature = hmac.new(
        settings.jwt_secret.encode(),
        payload_str.encode(),
        hashlib.sha256,
    ).hexdigest()[:16]
    signed_payload = f"{payload_str}:{signature}"

    # Get recipient's display name if we have their Slack ID
    recipient_name = None
    if recipient_slack_id:
        try:
            user_info = await slack_service.get_user_info(recipient_slack_id)
            recipient_name = (
                user_info.get("real_name")
                or user_info.get("profile", {}).get("display_name")
                or user_info.get("name")
            )
        except Exception as e:
            logger.warning(f"Could not get recipient name: {e}")

    # Build the message
    if recipient_name:
        header = f"Hello! I noticed you're trying to message *{recipient_name}*."
        intro = f"They are currently in focus mode and have notifications disabled."
    else:
        header = "Hello!"
        intro = "The person you're trying to reach is in focus mode and has notifications disabled."

    user_message = custom_message or "I'm currently in focus mode and not available."

    blocks = [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"{header}\n\n{intro}\n\nThey have left the following message:\n\n> _{user_message}_",
            },
        },
        {
            "type": "actions",
            "elements": [
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "Urgent - Notify Them"},
                    "style": "danger",
                    "action_id": "focus_bypass",
                    "value": signed_payload,
                },
            ],
        },
    ]

    await slack_service.client.chat_postMessage(
        channel=channel_id,
        text=f"Focus Mode: {recipient_name or 'User'} is unavailable - {user_message}",
        blocks=blocks,
        thread_ts=thread_ts,
    )


def _strip_bot_mention(text: str) -> str:
    """Remove bot mention from message text."""
    import re

    # Remove <@BOT_ID> mentions
    return re.sub(r"<@[A-Z0-9]+>\s*", "", text).strip()


def _extract_mentioned_user_ids(text: str) -> list[str]:
    """Extract all mentioned Slack user IDs from message text."""
    import re

    # Find all <@USERID> patterns
    return re.findall(r"<@([A-Z0-9]+)>", text)


@router.post("/commands")
async def handle_slack_commands(
    request: Request,
    background_tasks: BackgroundTasks,
) -> dict[str, Any]:
    """
    Handle Slack slash commands.

    Supported commands:
    - /alfred-link: Generate a linking code
    - /alfred-focus: Toggle focus mode
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
    text = form_data.get("text", "").strip()

    if command == "/alfred-link":
        return await handle_link_command(slack_user_id)

    if command == "/alfred-focus":
        # Process focus command in background for faster response
        background_tasks.add_task(
            process_focus_command_background, slack_user_id, text
        )
        return {
            "response_type": "ephemeral",
            "text": "Processing focus mode command...",
        }

    return {
        "response_type": "ephemeral",
        "text": f"Unknown command: {command}",
    }


async def process_focus_command_background(slack_user_id: str, text: str) -> None:
    """Process /alfred-focus command in background."""
    async for db in get_db():
        try:
            await handle_focus_command(slack_user_id, text, db)
        except Exception as e:
            logger.error(f"Error processing focus command: {e}")


async def handle_focus_command(
    slack_user_id: str, text: str, db
) -> dict[str, Any]:
    """
    Handle /alfred-focus command.

    Subcommands:
    - (empty): Toggle focus mode
    - on [duration]: Enable with optional duration (e.g., "2h", "30m")
    - off: Disable
    - status: Show current status
    - pomodoro: Start pomodoro mode
    """
    user_repo = UserRepository(db)
    user = await user_repo.get_by_slack_id(slack_user_id)

    slack_service = get_slack_service()

    if not user:
        # Can't respond directly, but log it
        logger.warning(f"Focus command from unlinked Slack user: {slack_user_id}")
        return {"response_type": "ephemeral", "text": "Please link your Slack account first."}

    focus_service = FocusModeService(db)
    notification_service = NotificationService(db)

    parts = text.lower().split()
    subcommand = parts[0] if parts else ""

    if subcommand == "off":
        await focus_service.disable(user.id)
        await notification_service.publish(user.id, "focus_ended", {})
        await slack_service.send_message(
            channel=slack_user_id,
            text=":bell: Focus mode disabled. You're now available.",
        )

    elif subcommand == "status":
        status = await focus_service.get_status(user.id)
        if status.is_active:
            remaining = ""
            if status.time_remaining_seconds:
                mins = status.time_remaining_seconds // 60
                remaining = f" ({mins} minutes remaining)"
            mode_text = "Pomodoro" if status.mode == "pomodoro" else "Focus"
            phase = f" - {status.pomodoro_phase} phase" if status.pomodoro_phase else ""
            await slack_service.send_message(
                channel=slack_user_id,
                text=f":no_bell: {mode_text} mode is *active*{phase}{remaining}",
            )
        else:
            await slack_service.send_message(
                channel=slack_user_id,
                text=":bell: Focus mode is *off*. You're available.",
            )

    elif subcommand == "pomodoro":
        await focus_service.start_pomodoro(user.id)
        await notification_service.publish(
            user.id,
            "pomodoro_work_started",
            {"session_count": 1},
        )
        await slack_service.send_message(
            channel=slack_user_id,
            text=":tomato: Pomodoro mode started! Focus time begins now.",
        )

    elif subcommand == "on" or subcommand == "":
        # Parse optional duration
        duration_minutes = None
        if len(parts) > 1:
            duration_str = parts[1]
            duration_minutes = _parse_duration(duration_str)

        if subcommand == "" and await focus_service.is_in_focus_mode(user.id):
            # Toggle off
            await focus_service.disable(user.id)
            await notification_service.publish(user.id, "focus_ended", {})
            await slack_service.send_message(
                channel=slack_user_id,
                text=":bell: Focus mode disabled. You're now available.",
            )
        else:
            # Enable focus mode
            await focus_service.enable(user.id, duration_minutes=duration_minutes)
            await notification_service.publish(
                user.id,
                "focus_started",
                {"duration_minutes": duration_minutes},
            )
            duration_text = f" for {duration_minutes} minutes" if duration_minutes else ""
            await slack_service.send_message(
                channel=slack_user_id,
                text=f":no_bell: Focus mode enabled{duration_text}. Messages will be auto-replied.",
            )

    else:
        await slack_service.send_message(
            channel=slack_user_id,
            text=(
                "Usage: `/alfred-focus [command]`\n"
                "Commands:\n"
                "• (empty) - Toggle focus mode\n"
                "• `on [duration]` - Enable (e.g., `on 2h`, `on 30m`)\n"
                "• `off` - Disable\n"
                "• `status` - Show current status\n"
                "• `pomodoro` - Start pomodoro mode"
            ),
        )

    return {"ok": True}


def _parse_duration(duration_str: str) -> int | None:
    """Parse duration string like '2h', '30m', '90' into minutes."""
    duration_str = duration_str.lower().strip()
    try:
        if duration_str.endswith("h"):
            return int(duration_str[:-1]) * 60
        elif duration_str.endswith("m"):
            return int(duration_str[:-1])
        else:
            return int(duration_str)
    except ValueError:
        return None


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


@router.post("/interactive")
async def handle_slack_interactive(
    request: Request,
    background_tasks: BackgroundTasks,
) -> dict[str, Any]:
    """
    Handle Slack interactive component callbacks.

    Handles button clicks, menu selections, etc.
    """
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

    # Parse the payload (URL encoded with 'payload' key containing JSON)
    form_data = await request.form()
    payload_str = form_data.get("payload", "")

    try:
        payload = json.loads(payload_str)
    except json.JSONDecodeError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid payload",
        )

    # Handle different action types
    actions = payload.get("actions", [])
    for action in actions:
        action_id = action.get("action_id")

        if action_id == "focus_bypass":
            # Process bypass in background
            background_tasks.add_task(
                process_bypass_background,
                action.get("value", ""),
                payload.get("user", {}).get("id", ""),
                payload.get("channel", {}).get("id", ""),
            )
            return {
                "response_action": "update",
                "text": ":rotating_light: Urgent notification sent!",
            }

    return {"ok": True}


async def process_bypass_background(
    signed_payload: str,
    sender_slack_id: str,
    channel_id: str,
) -> None:
    """Process focus bypass button click in background."""
    async for db in get_db():
        try:
            await handle_focus_bypass(signed_payload, sender_slack_id, channel_id, db)
        except Exception as e:
            logger.error(f"Error processing focus bypass: {e}")


async def handle_focus_bypass(
    signed_payload: str,
    sender_slack_id: str,
    channel_id: str,
    db,
) -> None:
    """Handle focus mode bypass button click."""
    settings = get_settings()
    slack_service = get_slack_service()

    # Validate signed payload
    try:
        parts = signed_payload.split(":")
        if len(parts) != 4:
            logger.warning("Invalid bypass payload format")
            return

        user_id, original_sender, timestamp_str, signature = parts

        # Verify signature
        payload_str = f"{user_id}:{original_sender}:{timestamp_str}"
        expected_sig = hmac.new(
            settings.jwt_secret.encode(),
            payload_str.encode(),
            hashlib.sha256,
        ).hexdigest()[:16]

        if not hmac.compare_digest(signature, expected_sig):
            logger.warning("Invalid bypass signature")
            return

        # Check timestamp (1 hour expiry)
        timestamp = int(timestamp_str)
        if abs(time.time() - timestamp) > 3600:
            logger.warning("Expired bypass payload")
            return

    except (ValueError, IndexError) as e:
        logger.warning(f"Error parsing bypass payload: {e}")
        return

    # Get sender info for notification
    try:
        sender_info = await slack_service.get_user_info(sender_slack_id)
        sender_name = sender_info.get("real_name") or sender_info.get("name", "Someone")
    except Exception:
        sender_name = "Someone"

    # Publish bypass notification
    notification_service = NotificationService(db)
    await notification_service.publish(
        user_id,
        "focus_bypass",
        {
            "sender_slack_id": sender_slack_id,
            "sender_name": sender_name,
            "channel_id": channel_id,
            "message": f"{sender_name} is trying to reach you urgently!",
        },
    )

    logger.info(f"Focus bypass notification sent for user {user_id} from {sender_name}")
