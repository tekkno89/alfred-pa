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


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan handler for startup and shutdown."""
    # Startup
    # TODO: Initialize database connections, redis, etc.
    yield
    # Shutdown
    # TODO: Close database connections, redis, etc.


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
