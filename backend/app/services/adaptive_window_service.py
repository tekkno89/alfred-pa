"""Adaptive delivery window service with EMA learning."""

import logging
from datetime import datetime, UTC

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.triage import AdaptiveWindow, MessageType

logger = logging.getLogger(__name__)

STARTER_WINDOWS: dict[str, int] = {
    "pr_review_request": 30,
    "direct_question": 30,
    "mention": 30,
    "discussion_relevant": 60,
    "announcement": 1440,
    "informational": 1440,
}

EMA_ALPHA = 0.2
MIN_SAMPLES = 5
MAX_SHIFT_FRACTION = 0.5
WINDOW_FLOOR = 15
WINDOW_CEILING = 1440


class AdaptiveWindowService:
    """Service for managing adaptive delivery windows with EMA learning."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_window(self, user_id: str, message_type_name: str) -> int:
        """Get the current delivery window for a message type.

        Returns the starter window if no learned window exists yet.
        """
        starter = STARTER_WINDOWS.get(message_type_name, 60)

        result = await self.db.execute(
            select(AdaptiveWindow)
            .join(MessageType, AdaptiveWindow.message_type_id == MessageType.id)
            .where(AdaptiveWindow.user_id == user_id)
            .where(MessageType.type_name == message_type_name)
        )
        window = result.scalar_one_or_none()

        if not window or window.sample_count < MIN_SAMPLES:
            return starter

        return window.window_minutes

    async def record_engagement(
        self, user_id: str, message_type_name: str, actual_delay_minutes: int
    ) -> int:
        """Record engagement and update window using EMA.

        Args:
            user_id: User ID
            message_type_name: Name of the message type
            actual_delay_minutes: Actual time taken to engage (minutes)

        Returns:
            Updated window value in minutes
        """
        msg_type_result = await self.db.execute(
            select(MessageType)
            .where(MessageType.user_id == user_id)
            .where(MessageType.type_name == message_type_name)
        )
        message_type = msg_type_result.scalar_one_or_none()

        if not message_type:
            logger.warning(
                f"MessageType '{message_type_name}' not found for user {user_id}"
            )
            return STARTER_WINDOWS.get(message_type_name, 60)

        result = await self.db.execute(
            select(AdaptiveWindow).where(
                AdaptiveWindow.user_id == user_id,
                AdaptiveWindow.message_type_id == message_type.id,
            )
        )
        window = result.scalar_one_or_none()

        starter = STARTER_WINDOWS.get(message_type_name, 60)

        if not window:
            window = AdaptiveWindow(
                user_id=user_id,
                message_type_id=message_type.id,
                window_minutes=starter,
                sample_count=0,
                last_updated=datetime.now(UTC),
            )
            self.db.add(window)
            await self.db.flush()

        new_sample_count = window.sample_count + 1

        if new_sample_count < MIN_SAMPLES:
            window.sample_count = new_sample_count
            window.last_updated = datetime.now(UTC)
            await self.db.flush()
            return window.window_minutes

        current = window.window_minutes
        max_shift = int(current * MAX_SHIFT_FRACTION)

        raw_ema = EMA_ALPHA * actual_delay_minutes + (1 - EMA_ALPHA) * current

        if raw_ema > current:
            new_window = min(raw_ema, current + max_shift)
        else:
            new_window = max(raw_ema, current - max_shift)

        new_window = max(WINDOW_FLOOR, min(WINDOW_CEILING, int(new_window)))

        window.window_minutes = new_window
        window.sample_count = new_sample_count
        window.last_updated = datetime.now(UTC)
        await self.db.flush()

        logger.info(
            f"Updated window for {message_type_name}: {current}m -> {new_window}m "
            f"(actual={actual_delay_minutes}m, samples={new_sample_count})"
        )

        return new_window

    async def reset_window(self, user_id: str, message_type_name: str) -> int:
        """Reset a window to its starter value.

        Args:
            user_id: User ID
            message_type_name: Name of the message type

        Returns:
            Starter window value
        """
        msg_type_result = await self.db.execute(
            select(MessageType)
            .where(MessageType.user_id == user_id)
            .where(MessageType.type_name == message_type_name)
        )
        message_type = msg_type_result.scalar_one_or_none()

        starter = STARTER_WINDOWS.get(message_type_name, 60)

        if not message_type:
            return starter

        result = await self.db.execute(
            select(AdaptiveWindow).where(
                AdaptiveWindow.user_id == user_id,
                AdaptiveWindow.message_type_id == message_type.id,
            )
        )
        window = result.scalar_one_or_none()

        if window:
            window.window_minutes = starter
            window.sample_count = 0
            window.last_updated = datetime.now(UTC)
            await self.db.flush()

        return starter

    async def get_all_windows(self, user_id: str) -> list[dict]:
        """Get all windows for a user.

        Returns list of dicts with:
        - message_type_name
        - window_minutes
        - sample_count
        - is_learning (True if sample_count < MIN_SAMPLES)
        - last_updated
        """
        result = await self.db.execute(
            select(AdaptiveWindow, MessageType)
            .join(MessageType, AdaptiveWindow.message_type_id == MessageType.id)
            .where(AdaptiveWindow.user_id == user_id)
            .where(MessageType.is_archived == False)  # noqa: E712
        )
        rows = result.all()

        windows = []
        for window, msg_type in rows:
            windows.append(
                {
                    "message_type_name": msg_type.type_name,
                    "window_minutes": window.window_minutes,
                    "sample_count": window.sample_count,
                    "is_learning": window.sample_count < MIN_SAMPLES,
                    "last_updated": window.last_updated,
                }
            )

        return windows
