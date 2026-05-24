"""Transparency API for R-Transparency.

Users can view and delete learned data:
- Topic keywords
- Sender distributions
- Per-type delivery windows
"""

from datetime import datetime, timedelta

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select, desc

from app.api.deps import CurrentUser, DbSession
from app.db.models.triage import (
    SenderActionDistribution,
    TriageClassification,
    TriageFeedback,
)
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


@router.get("")
async def get_transparency_data(
    current_user: CurrentUser,
    db: DbSession,
) -> dict:
    """Get all transparency data for the current user."""
    await _check_triage_access(current_user.id, db, current_user.role)

    topic_service = TopicAffinityService(db)
    biases = await topic_service.get_biases(current_user.id)

    keywords = [
        {
            "keyword": b.keyword,
            "weight": b.weight,
            "source_category": b.source_category,
        }
        for b in biases
    ]

    sender_result = await db.execute(
        select(SenderActionDistribution)
        .where(SenderActionDistribution.user_id == current_user.id)
        .order_by(desc(SenderActionDistribution.sample_count))
        .limit(20)
    )
    sender_distributions = sender_result.scalars().all()

    sender_patterns = [
        {
            "sender_name": dist.sender_slack_id,
            "sender_slack_id": dist.sender_slack_id,
            "channel_name": dist.channel_id,
            "action_distribution": dist.action_distribution,
            "sample_count": dist.sample_count,
        }
        for dist in sender_distributions
    ]

    thirty_days_ago = datetime.utcnow() - timedelta(days=30)
    corrections_result = await db.execute(
        select(TriageFeedback, TriageClassification)
        .join(TriageClassification, TriageFeedback.classification_id == TriageClassification.id)
        .where(TriageFeedback.user_id == current_user.id)
        .where(TriageFeedback.was_correct == False)
        .where(TriageFeedback.created_at >= thirty_days_ago)
        .order_by(desc(TriageFeedback.created_at))
        .limit(10)
    )
    corrections_data = corrections_result.all()

    recent_corrections = [
        {
            "message_text": classification.abstract or classification.slack_permalink or "Message",
            "corrected_action": feedback.correct_action or feedback.correct_priority or "unknown",
            "created_at": feedback.created_at.isoformat(),
        }
        for feedback, classification in corrections_data
    ]

    last_keyword_update = max(
        (b.last_updated for b in biases),
        default=None
    )

    return {
        "keywords": keywords,
        "sender_patterns": sender_patterns,
        "recent_corrections": recent_corrections,
        "last_updated": last_keyword_update.isoformat() if last_keyword_update else None,
    }


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
