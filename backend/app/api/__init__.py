from fastapi import APIRouter

from app.api.sessions import router as sessions_router

router = APIRouter()


@router.get("/")
async def api_root() -> dict[str, str]:
    """API root endpoint."""
    return {"message": "Alfred AI Assistant API", "version": "0.1.0"}


# Include sub-routers
router.include_router(sessions_router, prefix="/sessions", tags=["sessions"])

# TODO: Include sub-routers for auth, memory, slack
# from app.api.auth import router as auth_router
# from app.api.memory import router as memory_router
# from app.api.slack import router as slack_router

# router.include_router(auth_router, prefix="/auth", tags=["auth"])
# router.include_router(memory_router, prefix="/memory", tags=["memory"])
# router.include_router(slack_router, prefix="/slack", tags=["slack"])
