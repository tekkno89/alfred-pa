"""Service for sending Slack re-authorization notifications."""

import logging
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.db.models.user import User
from app.db.repositories import OAuthTokenRepository
from app.services.slack import SlackService

logger = logging.getLogger(__name__)

REAUTH_DM_TEXT = (
    ":wave: Hi! Alfred has been updated with new Slack permissions "
    "(e.g. channel listing for triage). Your current connection is missing "
    "some of these scopes.\n\n"
    "Please visit *Settings > Integrations* in the Alfred web app and click "
    "*Re-authorize Slack* to grant the updated permissions."
)


async def send_reauth_notifications(
    db: AsyncSession,
    required_scopes: frozenset[str],
    slack_service: SlackService | None = None,
) -> int:
    """Send a one-time DM to each user whose Slack token is missing required scopes.

    Returns the number of DMs sent.
    """
    token_repo = OAuthTokenRepository(db)
    stale_tokens = await token_repo.get_stale_slack_tokens(required_scopes)

    if not stale_tokens:
        logger.info("No stale Slack tokens found — skipping reauth notifications")
        return 0

    if slack_service is None:
        from app.services.slack import get_slack_service
        slack_service = get_slack_service()

    sent = 0
    for token in stale_tokens:
        # Load the user to get their slack_user_id (DM channel target)
        result = await db.execute(
            select(User).where(User.id == token.user_id)
        )
        user = result.scalar_one_or_none()
        if not user or not user.slack_user_id:
            logger.debug(
                f"Skipping reauth DM for token {token.id}: no linked Slack user"
            )
            # Still mark as sent so we don't retry every startup
            token.reauth_dm_sent_at = datetime.utcnow()
            continue

        try:
            await slack_service.send_message(
                channel=user.slack_user_id,
                text=REAUTH_DM_TEXT,
            )
            token.reauth_dm_sent_at = datetime.utcnow()
            sent += 1
            logger.info(f"Sent reauth DM to user {user.id} (slack: {user.slack_user_id})")
        except Exception:
            logger.exception(
                f"Failed to send reauth DM to user {user.id}"
            )
            # Mark as sent to avoid spamming on every restart
            token.reauth_dm_sent_at = datetime.utcnow()

    await db.flush()
    return sent
