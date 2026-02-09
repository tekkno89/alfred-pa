"""Helper functions for scheduling ARQ jobs."""

import logging
import uuid
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
        # Use unique job ID to avoid conflicts with previous job results
        job_id = f"focus_expire_{user_id}_{uuid.uuid4().hex[:8]}"

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
            _job_id=job_id,
        )

        if job is None:
            logger.warning(f"Could not schedule focus expiration for user {user_id}")
            return None

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

    Note: With unique job IDs, we can't cancel specific jobs.
    The jobs will check if the session is still active and do nothing if not.

    Args:
        user_id: The user's ID

    Returns:
        True (jobs will self-cancel when they run)
    """
    logger.info(f"Focus expiration for user {user_id} will be ignored when it runs")
    return True


def _pomodoro_job_key(user_id: str) -> str:
    """Redis key for storing the current pomodoro job ID."""
    return f"pomodoro_job:{user_id}"


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

        # Cancel any existing job first
        await cancel_pomodoro_transition(user_id)

        # Use unique job ID to avoid conflicts with previous job results
        job_id = f"pomodoro_transition_{user_id}_{uuid.uuid4().hex[:8]}"

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
            _job_id=job_id,
        )

        if job is None:
            logger.warning(f"Could not schedule pomodoro transition for user {user_id}")
            return None

        # Store the job ID so we can cancel it later
        await pool.set(_pomodoro_job_key(user_id), job_id, ex=86400)  # 24h TTL

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
    Cancel a scheduled pomodoro transition job by removing it from the queue.

    Args:
        user_id: The user's ID

    Returns:
        True if cancelled successfully, False otherwise
    """
    try:
        pool = await get_redis_pool()

        # Get the stored job ID
        job_id = await pool.get(_pomodoro_job_key(user_id))
        if not job_id:
            logger.info(f"No pomodoro job to cancel for user {user_id}")
            return True

        if isinstance(job_id, bytes):
            job_id = job_id.decode()

        # Remove from the queue (sorted set)
        queue_name = pool.default_queue_name
        removed = await pool.zrem(queue_name, job_id)

        # Clean up the job data
        await pool.delete(f"arq:job:{job_id}")

        # Remove our tracking key
        await pool.delete(_pomodoro_job_key(user_id))

        if removed:
            logger.info(f"Cancelled pomodoro transition job {job_id} for user {user_id}")
        else:
            logger.info(f"Pomodoro job {job_id} for user {user_id} was not in queue (may have already run)")

        return True

    except Exception as e:
        logger.error(f"Failed to cancel pomodoro transition: {e}")
        return False
