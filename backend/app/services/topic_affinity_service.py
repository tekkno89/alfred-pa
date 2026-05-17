"""Topic affinity keyword extraction and bias computation.

R3d: Extract topical keywords from messages during classification,
store as per-user weighted lists with source tracking for audit.
"""

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.llm import LLMMessage, get_llm_provider
from app.db.models.triage import TopicAffinity

if TYPE_CHECKING:
    from app.core.config import Settings

logger = logging.getLogger(__name__)

HALF_LIFE_DAYS = 30


@dataclass
class KeywordBias:
    """A topic keyword with its bias weight."""
    keyword: str
    weight: float
    source_category: str


class TopicAffinityService:
    """Manages per-user topic keywords for classifier bias.

    Keywords are extracted at classification time when message text
    is in memory. No raw text is persisted - only extracted keywords.

    Temporal decay: 30-day half-life applied during retrieval.
    """

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def extract_keywords(
        self,
        message_text: str,
    ) -> list[str]:
        """Extract topical keywords from a message using LLM.

        Returns list of keywords (max 5).
        """
        try:
            provider = get_llm_provider("gemini-2.0-flash")
            response = await provider.generate(
                messages=[
                    LLMMessage(
                        role="system",
                        content="Extract up to 5 topical keywords from this message. "
                        "Return ONLY a JSON array of strings, no other text.",
                    ),
                    LLMMessage(
                        role="user",
                        content=message_text[:500],  # Truncate long messages
                    ),
                ],
                temperature=0.1,
                max_tokens=100,
            )

            # Parse JSON array
            import json
            keywords = json.loads(response.strip())
            if isinstance(keywords, list):
                return [k.lower().strip() for k in keywords if isinstance(k, str)][:5]
            return []

        except Exception as e:
            logger.warning(f"Failed to extract keywords: {e}")
            return []

    async def update_affinity(
        self,
        user_id: str,
        keywords: list[str],
        source_category: str,
        is_positive: bool = True,
    ) -> None:
        """Update keyword weights based on classification/correction.

        Args:
            user_id: User to update
            keywords: List of keywords from the message
            source_category: 'public', 'sensitive', or 'dm'
            is_positive: True for positive signal (engage), False for negative (ignore)
        """
        weight_delta = 0.2 if is_positive else -0.1

        for keyword in keywords:
            # Check if keyword exists
            result = await self.db.execute(
                select(TopicAffinity).where(
                    TopicAffinity.user_id == user_id,
                    TopicAffinity.keyword == keyword,
                )
            )
            existing = result.scalar_one_or_none()

            if existing:
                # Update weight with decay
                new_weight = existing.weight * 0.9 + weight_delta  # 10% decay
                existing.weight = max(-1.0, min(1.0, new_weight))  # Clamp
                existing.last_updated = datetime.utcnow()
            else:
                # Create new keyword
                affinity = TopicAffinity(
                    user_id=user_id,
                    keyword=keyword,
                    weight=weight_delta,
                    source_category=source_category,
                )
                self.db.add(affinity)

        await self.db.commit()

    async def get_biases(
        self,
        user_id: str,
    ) -> list[KeywordBias]:
        """Get all topic biases for a user with temporal decay applied.

        Returns keywords with weight > 0.1 (positive) or weight < -0.1 (negative).
        """
        result = await self.db.execute(
            select(TopicAffinity)
            .where(TopicAffinity.user_id == user_id)
            .where(TopicAffinity.weight != 0)
            .order_by(TopicAffinity.weight.desc())
            .limit(100)
        )
        affinities = result.scalars().all()

        biases = []
        for affinity in affinities:
            # Apply temporal decay
            age_days = (datetime.utcnow() - affinity.last_updated).days
            decay_factor = 0.5 ** (age_days / HALF_LIFE_DAYS)
            decayed_weight = affinity.weight * decay_factor

            if abs(decayed_weight) > 0.1:
                biases.append(KeywordBias(
                    keyword=affinity.keyword,
                    weight=decayed_weight,
                    source_category=affinity.source_category,
                ))

        return biases

    async def delete_keyword(
        self,
        user_id: str,
        keyword: str,
    ) -> bool:
        """Delete a learned keyword. Returns True if deleted."""
        result = await self.db.execute(
            delete(TopicAffinity).where(
                TopicAffinity.user_id == user_id,
                TopicAffinity.keyword == keyword,
            )
        )
        await self.db.commit()
        return result.rowcount > 0

    async def delete_by_category(
        self,
        user_id: str,
        source_category: str,
    ) -> int:
        """Delete all keywords from a category. Returns count deleted."""
        result = await self.db.execute(
            delete(TopicAffinity).where(
                TopicAffinity.user_id == user_id,
                TopicAffinity.source_category == source_category,
            )
        )
        await self.db.commit()
        return result.rowcount
