"""Timezone service for resolving user timezones."""

import logging
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import User

logger = logging.getLogger(__name__)


COMMON_TIMEZONES = [
    # Americas
    ("America/New_York", "Eastern Time (US)"),
    ("America/Chicago", "Central Time (US)"),
    ("America/Denver", "Mountain Time (US)"),
    ("America/Los_Angeles", "Pacific Time (US)"),
    ("America/Anchorage", "Alaska Time"),
    ("Pacific/Honolulu", "Hawaii Time"),
    ("America/Toronto", "Toronto"),
    ("America/Vancouver", "Vancouver"),
    ("America/Mexico_City", "Mexico City"),
    ("America/Sao_Paulo", "Sao Paulo"),
    ("America/Buenos_Aires", "Buenos Aires"),
    # Europe
    ("Europe/London", "London"),
    ("Europe/Paris", "Paris"),
    ("Europe/Berlin", "Berlin"),
    ("Europe/Madrid", "Madrid"),
    ("Europe/Rome", "Rome"),
    ("Europe/Amsterdam", "Amsterdam"),
    ("Europe/Stockholm", "Stockholm"),
    ("Europe/Moscow", "Moscow"),
    # Asia
    ("Asia/Tokyo", "Tokyo"),
    ("Asia/Shanghai", "Shanghai"),
    ("Asia/Hong_Kong", "Hong Kong"),
    ("Asia/Singapore", "Singapore"),
    ("Asia/Seoul", "Seoul"),
    ("Asia/Mumbai", "Mumbai"),
    ("Asia/Dubai", "Dubai"),
    ("Asia/Bangkok", "Bangkok"),
    # Pacific
    ("Australia/Sydney", "Sydney"),
    ("Australia/Melbourne", "Melbourne"),
    ("Australia/Perth", "Perth"),
    ("Pacific/Auckland", "Auckland"),
]


async def get_user_timezone(db: AsyncSession, user_id: str) -> str:
    """
    Get user's timezone with fallback chain.

    Resolution order:
    1. User's stored timezone preference
    2. Slack profile timezone (if available)
    3. UTC (default)

    Returns IANA timezone string (e.g., 'America/Los_Angeles', 'UTC')
    """
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user:
        logger.warning(f"User {user_id} not found, defaulting to UTC")
        return "UTC"

    if user.timezone:
        return user.timezone

    return "UTC"


async def get_user_timezone_with_slack(
    db: AsyncSession, user_id: str, slack_user_id: str | None = None
) -> str:
    """
    Get user's timezone including Slack profile lookup.

    Resolution order:
    1. User's stored timezone preference
    2. Slack profile timezone (if connected)
    3. UTC (default)
    """
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user:
        logger.warning(f"User {user_id} not found, defaulting to UTC")
        return "UTC"

    if user.timezone:
        return user.timezone

    if user.slack_user_id:
        try:
            from app.services.slack_user import SlackUserService

            slack_service = SlackUserService(db)
            user_info = await slack_service.get_user_info(user.slack_user_id)
            if user_info and user_info.get("tz"):
                return user_info["tz"]
        except Exception as e:
            logger.warning(f"Failed to fetch Slack timezone for user {user_id}: {e}")

    return "UTC"


def get_current_time_in_tz(tz_name: str) -> datetime:
    """
    Get current time in a specific timezone.

    Args:
        tz_name: IANA timezone string (e.g., 'America/Los_Angeles')

    Returns:
        datetime object with timezone info
    """
    try:
        tz = ZoneInfo(tz_name)
        return datetime.now(tz)
    except Exception as e:
        logger.warning(f"Invalid timezone '{tz_name}', falling back to UTC: {e}")
        return datetime.now(timezone.utc)


def convert_utc_to_local(utc_dt: datetime, tz_name: str) -> datetime:
    """
    Convert a UTC datetime to local time in the given timezone.

    Args:
        utc_dt: datetime in UTC (should have tzinfo set or be naive UTC)
        tz_name: IANA timezone string

    Returns:
        datetime in the local timezone
    """
    if utc_dt.tzinfo is None:
        utc_dt = utc_dt.replace(tzinfo=timezone.utc)

    try:
        tz = ZoneInfo(tz_name)
        return utc_dt.astimezone(tz)
    except Exception:
        return utc_dt


def get_timezone_display_name(tz_name: str) -> str:
    """Get a human-readable display name for a timezone."""
    for tz_id, display_name in COMMON_TIMEZONES:
        if tz_id == tz_name:
            return display_name
    return tz_name
