"""ARQ worker configuration and tasks."""

import logging

from arq import cron
from arq.connections import RedisSettings

from app.core.config import get_settings
from app.worker.tasks import (
    check_due_todo_reminders,
    cleanup_expired_classifications,
    expire_focus_session,
    process_triage_job,
    refresh_slack_channel_cache,
    send_todo_reminder,
    transition_pomodoro,
    update_channel_summaries,
    update_user_channel_participation,
)

logger = logging.getLogger(__name__)

# Configure logging for worker
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)


async def startup(ctx: dict) -> None:
    """Called when worker starts."""
    logger.info("ARQ worker starting up")

    # Rebuild triage monitored channels Redis set
    try:
        from app.db.session import async_session_maker
        from app.services.triage_cache import TriageCacheService

        async with async_session_maker() as db:
            cache = TriageCacheService()
            await cache.rebuild_set(db)
    except Exception:
        logger.exception("Failed to rebuild triage monitored channels set on startup")

    # Pre-populate Slack channel cache on deploy
    try:
        await refresh_slack_channel_cache(ctx)
    except Exception:
        logger.exception("Failed to pre-populate Slack channel cache on startup")

    # Bootstrap channel participation data on first deploy
    try:
        await update_user_channel_participation(ctx)
    except Exception:
        logger.exception("Failed to bootstrap channel participation on startup")


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
        send_todo_reminder,
        process_triage_job,
        refresh_slack_channel_cache,
        update_user_channel_participation,
        update_channel_summaries,
    ]

    # Cron jobs (optional - for periodic cleanup as backup)
    cron_jobs = [
        cron(
            expire_focus_session,
            minute={0, 15, 30, 45},  # Run every 15 minutes as backup
            run_at_startup=True,
        ),
        cron(
            check_due_todo_reminders,
            minute={0, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55},  # Every 5 minutes
        ),
        cron(
            cleanup_expired_classifications,
            hour={3},
            minute={0},  # Daily at 3 AM
        ),
        cron(
            refresh_slack_channel_cache,
            minute={0},  # Hourly
        ),
        cron(
            update_user_channel_participation,
            hour={6},
            minute={0},  # Daily at 6 AM UTC
        ),
        cron(
            update_channel_summaries,
            weekday={0},
            hour={7},
            minute={0},  # Monday 7 AM UTC
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
