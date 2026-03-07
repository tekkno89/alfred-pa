from fastapi import APIRouter

from app.api.auth import router as auth_router
from app.api.focus import router as focus_router
from app.api.memories import router as memories_router
from app.api.notifications import router as notifications_router
from app.api.sessions import router as sessions_router
from app.api.slack import router as slack_router
from app.api.webhooks import router as webhooks_router
from app.api.notes import router as notes_router
from app.api.todos import router as todos_router
from app.api.dashboard import router as dashboard_router
from app.api.admin import router as admin_router
from app.api.github import router as github_router
from app.api.google_calendar import router as google_calendar_router
from app.api.calendar import router as calendar_router

router = APIRouter()


@router.get("/")
async def api_root() -> dict[str, str]:
    """API root endpoint."""
    return {"message": "Alfred AI Assistant API", "version": "0.1.0"}


# Include sub-routers
router.include_router(auth_router, prefix="/auth", tags=["auth"])
router.include_router(focus_router, prefix="/focus", tags=["focus"])
router.include_router(memories_router, prefix="/memories", tags=["memories"])
router.include_router(notifications_router, prefix="/notifications", tags=["notifications"])
router.include_router(sessions_router, prefix="/sessions", tags=["sessions"])
router.include_router(slack_router, prefix="/slack", tags=["slack"])
router.include_router(webhooks_router, prefix="/webhooks", tags=["webhooks"])
router.include_router(notes_router, prefix="/notes", tags=["notes"])
router.include_router(todos_router, prefix="/todos", tags=["todos"])
router.include_router(dashboard_router, prefix="/dashboard", tags=["dashboard"])
router.include_router(admin_router, prefix="/admin", tags=["admin"])
router.include_router(github_router, prefix="/github", tags=["github"])
router.include_router(google_calendar_router, prefix="/google-calendar", tags=["google-calendar"])
router.include_router(calendar_router, prefix="/calendar", tags=["calendar"])
