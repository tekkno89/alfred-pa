"""Helper functions for scheduling ARQ jobs."""

import logging
from datetime import datetime

from arq import create_pool
from arq.connections import RedisSettings

from app.core.config import get_settings

logger = logging.getLogger(__name__)

_pool = None


async def get_redis_pool():
    """Get or create the ARQ Redis connection pool."""
    global _pool
    if _pool is None:
        settings = get_settings()
        redis_url = settings.redis_url
        if redis_url.startswith("redis://"):
            redis_url = redis_url[8:]
        host, port = redis_url.split(":")
        _pool = await create_pool(RedisSettings(host=host, port=int(port)))
    return _pool


async def schedule_focus_expiration(user_id: str, expires_at: datetime) -> str | None:
    """
    Schedule a job to expire a focus session at a specific time.

    Args:
        user_id: The user's ID
        expires_at: When the focus session should expire

    Returns:
        Job ID if scheduled successfully, None otherwise
    """
    try:
        pool = await get_redis_pool()

        # Calculate delay from now
        now = datetime.utcnow()
        if expires_at <= now:
            # Already expired, run immediately
            delay_seconds = 0
        else:
            delay_seconds = (expires_at - now).total_seconds()

        job = await pool.enqueue_job(
            "expire_focus_session",
            user_id,
            _defer_by=delay_seconds,
            _job_id=f"focus_expire_{user_id}",
        )

        logger.info(
            f"Scheduled focus expiration for user {user_id} "
            f"in {delay_seconds:.0f} seconds (job_id={job.job_id})"
        )
        return job.job_id

    except Exception as e:
        logger.error(f"Failed to schedule focus expiration: {e}")
        return None


async def cancel_focus_expiration(user_id: str) -> bool:
    """
    Cancel a scheduled focus expiration job.

    Args:
        user_id: The user's ID

    Returns:
        True if cancelled, False otherwise
    """
    try:
        pool = await get_redis_pool()
        job_id = f"focus_expire_{user_id}"

        # ARQ doesn't have a direct cancel method, but we can abort the job
        # by checking if it exists and removing it from the queue
        job = await pool.job(job_id)
        if job:
            await job.abort()
            logger.info(f"Cancelled focus expiration job for user {user_id}")
            return True
        else:
            logger.info(f"No focus expiration job found for user {user_id}")
            return False

    except Exception as e:
        logger.error(f"Failed to cancel focus expiration: {e}")
        return False


async def schedule_pomodoro_transition(user_id: str, transition_at: datetime) -> str | None:
    """
    Schedule a job to transition pomodoro phase at a specific time.

    Args:
        user_id: The user's ID
        transition_at: When the pomodoro phase should transition

    Returns:
        Job ID if scheduled successfully, None otherwise
    """
    try:
        pool = await get_redis_pool()

        # Calculate delay from now
        now = datetime.utcnow()
        if transition_at <= now:
            delay_seconds = 0
        else:
            delay_seconds = (transition_at - now).total_seconds()

        job = await pool.enqueue_job(
            "transition_pomodoro",
            user_id,
            _defer_by=delay_seconds,
            _job_id=f"pomodoro_transition_{user_id}",
        )

        logger.info(
            f"Scheduled pomodoro transition for user {user_id} "
            f"in {delay_seconds:.0f} seconds (job_id={job.job_id})"
        )
        return job.job_id

    except Exception as e:
        logger.error(f"Failed to schedule pomodoro transition: {e}")
        return None


async def cancel_pomodoro_transition(user_id: str) -> bool:
    """
    Cancel a scheduled pomodoro transition job.

    Args:
        user_id: The user's ID

    Returns:
        True if cancelled, False otherwise
    """
    try:
        pool = await get_redis_pool()
        job_id = f"pomodoro_transition_{user_id}"

        job = await pool.job(job_id)
        if job:
            await job.abort()
            logger.info(f"Cancelled pomodoro transition job for user {user_id}")
            return True
        else:
            logger.info(f"No pomodoro transition job found for user {user_id}")
            return False

    except Exception as e:
        logger.error(f"Failed to cancel pomodoro transition: {e}")
        return False
