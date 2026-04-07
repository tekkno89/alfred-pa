import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import make_asgi_app

from app.core.config import get_settings
from app.api import router as api_router


settings = get_settings()


class _SuppressPollingFilter(logging.Filter):
    """Filter out noisy polling endpoint access logs."""

    _SUPPRESSED = ("/health", "/api/focus/status")

    def filter(self, record: logging.LogRecord) -> bool:
        msg = record.getMessage()
        return not any(path in msg for path in self._SUPPRESSED)


logging.getLogger("uvicorn.access").addFilter(_SuppressPollingFilter())

# Set Slack event handler log level based on SLACK_DEBUG env var
if settings.slack_debug:
    logging.getLogger("app.api.slack").setLevel(logging.DEBUG)


async def _handle_coding_event(topic: str, payload: dict) -> None:
    """Handle coding job completion/failure events from the event bus."""
    from app.db.session import async_session_maker
    from app.services.coding_job import CodingJobService

    job_id = payload.get("job_id")
    if not job_id:
        logging.getLogger(__name__).warning(
            f"EventBus: coding event missing job_id: {topic}"
        )
        return

    async with async_session_maker() as db:
        try:
            service = CodingJobService(db)
            if payload.get("success", False):
                output_files = payload.get("output_files", {})
                await service.handle_container_complete(job_id, output_files)
            else:
                error = payload.get("error", "Unknown error")
                logs = payload.get("logs")
                await service.handle_container_failed(job_id, error, logs)
            await db.commit()
        except Exception:
            await db.rollback()
            logging.getLogger(__name__).exception(
                f"EventBus: error handling coding event for job {job_id}"
            )


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan handler for startup and shutdown."""
    import asyncio
    from app.services.notifications import NotificationService

    # Validate config and log issues
    from app.core.config_validator import log_config_issues
    log_config_issues(get_settings())

    # Start Redis pub/sub subscriber for cross-process SSE delivery
    subscriber_task = asyncio.create_task(NotificationService.start_redis_subscriber())

    # Start event bus subscriber for coding job completion events
    event_bus = None
    try:
        from app.core.events import get_event_bus

        event_bus = get_event_bus()
        await event_bus.subscribe("coding.*", _handle_coding_event)
        await event_bus.start()
    except Exception:
        logging.getLogger(__name__).exception(
            "Failed to start event bus — coding completion events "
            "will rely on callback/polling fallback"
        )

    # Send one-time reauth DMs to users with stale Slack scopes
    try:
        from app.api.auth import REQUIRED_SLACK_USER_SCOPES
        from app.db.session import async_session_maker
        from app.services.slack_reauth import send_reauth_notifications

        async with async_session_maker() as db:
            try:
                sent = await send_reauth_notifications(db, REQUIRED_SLACK_USER_SCOPES)
                await db.commit()
                if sent:
                    logging.getLogger(__name__).info(
                        f"Sent {sent} Slack reauth notification(s)"
                    )
            except Exception:
                await db.rollback()
                logging.getLogger(__name__).exception(
                    "Failed to send Slack reauth notifications"
                )
    except Exception:
        logging.getLogger(__name__).exception(
            "Failed to initialize Slack reauth check"
        )

    yield

    # Shutdown
    if event_bus:
        await event_bus.stop()

    subscriber_task.cancel()
    try:
        await subscriber_task
    except asyncio.CancelledError:
        pass


app = FastAPI(
    title=settings.app_name,
    description="Personal AI Assistant with LangGraph",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.cors_origins.split(",")],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount Prometheus metrics endpoint
metrics_app = make_asgi_app()
app.mount("/metrics", metrics_app)

# Include API routes
app.include_router(api_router, prefix="/api")


@app.get("/health")
async def health_check() -> dict[str, str]:
    """Health check endpoint."""
    return {"status": "healthy"}
