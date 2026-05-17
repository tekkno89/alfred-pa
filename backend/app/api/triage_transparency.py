"""Transparency API for R-Transparency.

Users can view and delete learned data:
- Topic keywords
- Sender distributions
- Per-type delivery windows
"""

from fastapi import APIRouter, HTTPException, status

from app.api.deps import CurrentUser, DbSession
from app.db.repositories import FeatureAccessRepository
from app.services.topic_affinity_service import TopicAffinityService

router = APIRouter(prefix="/transparency", tags=["triage-transparency"])


async def _check_triage_access(user_id: str, db, role: str) -> None:
    """Check if user has triage feature access."""
    repo = FeatureAccessRepository(db)
    if role != "admin" and not await repo.is_enabled(user_id, "card:triage"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Triage feature not enabled",
        )


@router.get("/keywords")
async def list_learned_keywords(
    current_user: CurrentUser,
    db: DbSession,
) -> dict:
    """List all learned topic keywords for the current user."""
    await _check_triage_access(current_user.id, db, current_user.role)
    service = TopicAffinityService(db)
    biases = await service.get_biases(current_user.id)

    return {
        "keywords": [
            {
                "keyword": b.keyword,
                "weight": b.weight,
                "source_category": b.source_category,
            }
            for b in biases
        ]
    }


@router.delete("/keywords/{keyword}")
async def delete_keyword(
    keyword: str,
    current_user: CurrentUser,
    db: DbSession,
) -> dict:
    """Delete a learned topic keyword."""
    await _check_triage_access(current_user.id, db, current_user.role)
    service = TopicAffinityService(db)
    deleted = await service.delete_keyword(current_user.id, keyword)

    if not deleted:
        raise HTTPException(status_code=404, detail="Keyword not found")

    return {"deleted": True}


@router.delete("/keywords/category/{category}")
async def delete_keywords_by_category(
    category: str,
    current_user: CurrentUser,
    db: DbSession,
) -> dict:
    """Delete all keywords from a source category."""
    if category not in ("public", "sensitive", "dm"):
        raise HTTPException(status_code=400, detail="Invalid category")

    await _check_triage_access(current_user.id, db, current_user.role)
    service = TopicAffinityService(db)
    count = await service.delete_by_category(current_user.id, category)

    return {"deleted_count": count}
