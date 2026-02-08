from fastapi import APIRouter

from app.api.auth import router as auth_router
from app.api.memories import router as memories_router
from app.api.sessions import router as sessions_router
from app.api.slack import router as slack_router

router = APIRouter()


@router.get("/")
async def api_root() -> dict[str, str]:
    """API root endpoint."""
    return {"message": "Alfred AI Assistant API", "version": "0.1.0"}


# Include sub-routers
router.include_router(auth_router, prefix="/auth", tags=["auth"])
router.include_router(memories_router, prefix="/memories", tags=["memories"])
router.include_router(sessions_router, prefix="/sessions", tags=["sessions"])
router.include_router(slack_router, prefix="/slack", tags=["slack"])
