"""ARQ worker configuration and tasks."""

import logging

from arq import cron
from arq.connections import RedisSettings

from app.core.config import get_settings
from app.worker.tasks import expire_focus_session, transition_pomodoro

logger = logging.getLogger(__name__)

# Configure logging for worker
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)


async def startup(ctx: dict) -> None:
    """Called when worker starts."""
    logger.info("ARQ worker starting up")


async def shutdown(ctx: dict) -> None:
    """Called when worker shuts down."""
    logger.info("ARQ worker shutting down")


def get_redis_settings() -> RedisSettings:
    """Get Redis settings from environment."""
    settings = get_settings()
    # Parse redis URL (redis://host:port)
    redis_url = settings.redis_url
    if redis_url.startswith("redis://"):
        redis_url = redis_url[8:]
    host, port = redis_url.split(":")
    return RedisSettings(host=host, port=int(port))


class WorkerSettings:
    """ARQ worker settings."""

    # Redis connection
    redis_settings = get_redis_settings()

    # Functions that can be called as tasks
    functions = [
        expire_focus_session,
        transition_pomodoro,
    ]

    # Cron jobs (optional - for periodic cleanup as backup)
    cron_jobs = [
        cron(
            expire_focus_session,
            minute={0, 15, 30, 45},  # Run every 15 minutes as backup
            run_at_startup=True,
        ),
    ]

    # Lifecycle hooks
    on_startup = startup
    on_shutdown = shutdown

    # Job settings
    max_jobs = 10
    job_timeout = 300  # 5 minutes
    keep_result = 3600  # Keep results for 1 hour
    queue_name = "arq:queue"
