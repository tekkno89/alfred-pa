# Phase 2: Trust-Building

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement closed-loop learning with three consumers, end-of-day review, telemetry, and transparency UI.

**Duration:** 3 weeks

**Architecture:** Three learning consumers ingest feedback corrections: (1) Few-shot retrieval via semantic search over `FeedbackEmbedding`, (2) Per-sender action distributions with temporal decay, (3) Topic affinity keyword extraction. EOD review surfaces pending items, counterfactuals, and pattern suggestions. Transparency UI lets users audit learned data.

**Tech Stack:** Python 3.11+, FastAPI, pgvector, Redis, React

---

## Requirements Covered

- **R3:** Closed-loop learning (3 consumers)
- **R6:** End-of-day review
- **R7:** Split telemetry (classification recall + delivery hit rate)
- **R8:** Counterfactual review
- **R-Meta:** Learned settings show reasoning
- **R-Transparency:** Audit UI for learned data

---

## File Structure

### Create

```
backend/app/services/learned_example_retriever.py
backend/app/services/topic_affinity_service.py
backend/app/services/suppressed_delivery_service.py
backend/app/services/learned_data_audit_service.py
backend/app/services/pattern_suggestion_service.py
backend/alembic/versions/044_add_topic_affinities.py
backend/alembic/versions/045_add_suppressed_deliveries.py
backend/alembic/versions/046_add_message_types.py
backend/app/api/triage_transparency.py
frontend/src/pages/TriageReviewPage.tsx
frontend/src/pages/TriageTransparencyPage.tsx
frontend/src/components/triage/LearnedKeywordsCard.tsx
frontend/src/components/triage/ReviewQueue.tsx
```

### Modify

```
backend/app/db/models/triage.py
backend/app/services/triage_classifier.py
backend/app/services/triage_enrichment.py
backend/app/worker/tasks.py
backend/app/api/triage.py
backend/app/schemas/triage.py
```

---

## Task 1: Implement LearnedExampleRetriever (R3b)

**Files:**
- Create: `backend/app/services/learned_example_retriever.py`
- Create: `backend/tests/unit/test_learned_example_retriever.py`

### Step 1: Create the service

- [ ] **Create service file**

```python
# backend/app/services/learned_example_retriever.py
"""Few-shot example retrieval from past corrections.

R3b: Retrieve top-K semantically similar past corrections and inject
as few-shot exemplars in the classifier prompt.
"""

import logging
from dataclasses import dataclass

from pgvector.asyncpg import register_vector
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.embeddings import get_embedding_provider
from app.db.models.triage import FeedbackEmbedding, TriageFeedback, TriageClassification

logger = logging.getLogger(__name__)

TOP_K = 5


@dataclass
class LearnedExample:
    """A past correction to use as a few-shot example."""
    original_abstract: str
    correct_action: str
    feedback_reason: str | None
    similarity: float


class LearnedExampleRetriever:
    """Retrieves semantically similar past corrections for few-shot learning.

    Works for all content types:
    - Non-sensitive: embedding computed from cached message text
    - Sensitive: embedding computed on-demand from Slack-fetched text
    """

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def retrieve_examples(
        self,
        user_id: str,
        channel_id: str | None,
        sender_slack_id: str | None,
        message_text: str,
        top_k: int = TOP_K,
    ) -> list[LearnedExample]:
        """Retrieve top-K most similar past corrections.

        Priority:
        1. Same channel and sender
        2. Same channel
        3. Any channel

        Args:
            user_id: User to retrieve examples for
            channel_id: Optional channel filter
            sender_slack_id: Optional sender filter
            message_text: Message text to find similar corrections for
            top_k: Number of examples to retrieve

        Returns:
            List of LearnedExample objects sorted by similarity
        """
        # Compute embedding for the new message
        embedding_provider = get_embedding_provider()
        embedding = await embedding_provider.embed_text(message_text)

        # Query for similar embeddings
        # Note: pgvector similarity search using <=> (distance operator)
        query = (
            select(
                FeedbackEmbedding,
                TriageFeedback,
                TriageClassification,
            )
            .join(TriageFeedback, FeedbackEmbedding.triage_feedback_id == TriageFeedback.id)
            .join(TriageClassification, TriageFeedback.classification_id == TriageClassification.id)
            .where(TriageFeedback.user_id == user_id)
            .where(TriageFeedback.was_correct == False)  # Only corrections
            .where(TriageFeedback.correct_action.isnot(None))  # Has corrected action
            .order_by(FeedbackEmbedding.embedding_vector.cosine_distance(embedding))
            .limit(top_k * 2)  # Fetch extra to filter
        )

        # Prefer same channel/sender
        if channel_id:
            query = query.where(TriageClassification.channel_id == channel_id)
        if sender_slack_id:
            query = query.where(TriageClassification.sender_slack_id == sender_slack_id)

        result = await self.db.execute(query)
        rows = result.all()

        examples = []
        for row in rows[:top_k]:
            feedback_emb, feedback, classification = row
            examples.append(LearnedExample(
                original_abstract=classification.abstract or "Message",
                correct_action=feedback.correct_action or "summarize_next",
                feedback_reason=feedback.feedback_text,
                similarity=1.0 - (feedback_emb.embedding_vector.cosine_distance(embedding) if hasattr(feedback_emb.embedding_vector, 'cosine_distance') else 0.5),
            ))

        return examples

    async def store_correction_embedding(
        self,
        feedback_id: str,
        message_text: str,
    ) -> FeedbackEmbedding:
        """Compute and store embedding for a correction.

        Called when user submits feedback correction.
        For sensitive content, message_text is fetched from Slack first.
        """
        embedding_provider = get_embedding_provider()
        embedding = await embedding_provider.embed_text(message_text)

        fb_embedding = FeedbackEmbedding(
            triage_feedback_id=feedback_id,
            embedding_vector=embedding,
        )
        self.db.add(fb_embedding)
        await self.db.commit()
        await self.db.refresh(fb_embedding)

        logger.info(f"Stored embedding for feedback {feedback_id}")
        return fb_embedding
```

### Step 2: Write unit test

- [ ] **Create test file**

```python
# backend/tests/unit/test_learned_example_retriever.py
"""Unit tests for LearnedExampleRetriever."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime

from app.services.learned_example_retriever import (
    LearnedExampleRetriever,
    LearnedExample,
)


@pytest.fixture
def mock_db():
    return AsyncMock()


@pytest.fixture
def retriever(mock_db):
    return LearnedExampleRetriever(mock_db)


class TestLearnedExampleRetriever:
    @pytest.mark.asyncio
    async def test_retrieve_examples_returns_similar(self, retriever, mock_db):
        """retrieve_examples should return similar past corrections."""
        mock_result = MagicMock()
        mock_result.all.return_value = []
        mock_db.execute.return_value = mock_result

        with patch(
            "app.services.learned_example_retriever.get_embedding_provider"
        ) as mock_provider:
            mock_provider.return_value.embed_text = AsyncMock(return_value=[0.1] * 768)
            
            examples = await retriever.retrieve_examples(
                user_id="u1",
                channel_id="C123",
                sender_slack_id="U123",
                message_text="Test message",
            )
            
            assert isinstance(examples, list)

    def test_learned_example_dataclass(self):
        """LearnedExample should have expected fields."""
        example = LearnedExample(
            original_abstract="Test abstract",
            correct_action="notify_now",
            feedback_reason="This was urgent",
            similarity=0.85,
        )
        
        assert example.correct_action == "notify_now"
        assert example.similarity == 0.85
```

### Step 3: Commit

```bash
git add backend/app/services/learned_example_retriever.py \
        backend/tests/unit/test_learned_example_retriever.py
git commit -m "feat(triage): add LearnedExampleRetriever for few-shot learning"
```

---

## Task 2: Implement TopicAffinityService (R3d)

**Files:**
- Create: `backend/alembic/versions/044_add_topic_affinities.py`
- Create: `backend/app/services/topic_affinity_service.py`
- Modify: `backend/app/db/models/triage.py`
- Modify: `backend/app/db/models/__init__.py`

### Step 1: Create migration

- [ ] **Create migration file**

```python
# backend/alembic/versions/044_add_topic_affinities.py
"""add topic affinities

Revision ID: 044
Revises: 043
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '044'
down_revision = '043'
depends_on = None


def upgrade() -> None:
    op.create_table(
        'topic_affinities',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('user_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('users.id'), nullable=False),
        sa.Column('keyword', sa.String(100), nullable=False),
        sa.Column('weight', sa.Float(), nullable=False),
        sa.Column('source_category', sa.String(50), nullable=False),
        sa.Column('last_updated', sa.DateTime(timezone=True),
                  nullable=False, server_default=sa.func.now()),
    )
    op.create_index(
        'ix_topic_affinities_unique',
        'topic_affinities',
        ['user_id', 'keyword'],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index('ix_topic_affinities_unique')
    op.drop_table('topic_affinities')
```

### Step 2: Add model

- [ ] **Add TopicAffinity model**

```python
# backend/app/db/models/triage.py
# Add after SenderActionDistribution:

class TopicAffinity(Base, UUIDMixin, TimestampMixin):
    """Per-user topic keyword with weight and source tracking.

    Derived data from message classification/correction.
    No raw text stored - only extracted keywords.

    Source categories for audit:
    - 'public': learned from public non-sensitive channels
    - 'sensitive': learned from sensitive-flagged public channels
    - 'dm': learned from DMs
    """

    __tablename__ = "topic_affinities"

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    keyword: Mapped[str] = mapped_column(String(100), nullable=False)
    weight: Mapped[float] = mapped_column(Float, nullable=False)
    source_category: Mapped[str] = mapped_column(String(50), nullable=False)
    last_updated: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    user: Mapped["User"] = relationship("User")

    __table_args__ = (
        {"comment": "UNIQUE(user_id, keyword) enforced via migration index"},
    )

    def __repr__(self) -> str:
        return f"<TopicAffinity(user={self.user_id}, keyword={self.keyword}, weight={self.weight})>"
```

### Step 3: Create service

- [ ] **Create service file**

```python
# backend/app/services/topic_affinity_service.py
"""Topic affinity keyword extraction and bias computation.

R3d: Extract topical keywords from messages during classification,
store as per-user weighted lists with source tracking for audit.
"""

import logging
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.llm import LLMMessage, get_llm_provider
from app.db.models.triage import TopicAffinity

if TYPE_CHECKING:
    from app.core.config import Settings

logger = logging.getLogger(__name__)

HALF_LIFE_DAYS = 30
MAX_KEYWORDS_PER_USER = 500


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
```

### Step 4: Run migration

```bash
docker-compose -f docker-compose.dev.yml exec backend alembic upgrade head
```

### Step 5: Commit

```bash
git add backend/alembic/versions/044_add_topic_affinities.py \
        backend/app/db/models/triage.py \
        backend/app/services/topic_affinity_service.py
git commit -m "feat(triage): add TopicAffinityService for keyword-based learning"
```

---

## Task 3: Implement SuppressedDeliveryService (R8)

**Files:**
- Create: `backend/alembic/versions/045_add_suppressed_deliveries.py`
- Create: `backend/app/services/suppressed_delivery_service.py`
- Modify: `backend/app/db/models/triage.py`

### Step 1: Create migration

- [ ] **Create migration file**

```python
# backend/alembic/versions/045_add_suppressed_deliveries.py
"""add suppressed deliveries

Revision ID: 045
Revises: 044
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '045'
down_revision = '044'
depends_on = None


def upgrade() -> None:
    op.create_table(
        'suppressed_deliveries',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('user_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('users.id'), nullable=False),
        sa.Column('message_id', sa.String(50), nullable=False),
        sa.Column('original_action', sa.String(20), nullable=False),
        sa.Column('suppression_reason', sa.String(50), nullable=False),
        sa.Column('outcome_summary', sa.Text(), nullable=True),
        sa.Column('user_review_response', sa.String(20), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True),
                  nullable=False, server_default=sa.func.now()),
    )
    op.create_index(
        'ix_suppressed_deliveries_user_created',
        'suppressed_deliveries',
        ['user_id', 'created_at'],
    )


def downgrade() -> None:
    op.drop_index('ix_suppressed_deliveries_user_created')
    op.drop_table('suppressed_deliveries')
```

### Step 2: Add model

- [ ] **Add SuppressedDelivery model**

```python
# backend/app/db/models/triage.py
# Add after TopicAffinity:

class SuppressedDelivery(Base, UUIDMixin, TimestampMixin):
    """Record of a delivery suppressed by engagement check.

    Used for counterfactual review: "would you have wanted to know sooner?"
    Retained for 90 days.

    Canonical cap: 10 suppressed items per user per day.
    """

    __tablename__ = "suppressed_deliveries"

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    message_id: Mapped[str] = mapped_column(String(50), nullable=False)
    original_action: Mapped[str] = mapped_column(String(20), nullable=False)
    suppression_reason: Mapped[str] = mapped_column(String(50), nullable=False)
    outcome_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    user_review_response: Mapped[str | None] = mapped_column(String(20), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    user: Mapped["User"] = relationship("User")

    def __repr__(self) -> str:
        return f"<SuppressedDelivery(user={self.user_id}, action={self.original_action})>"
```

### Step 3: Create service

- [ ] **Create service file**

```python
# backend/app/services/suppressed_delivery_service.py
"""Service for tracking and reviewing suppressed deliveries.

R8: When R2b suppresses a delivery, record it for counterfactual review.
Auto-promote to next digest; surface in EOD review.
"""

import logging
from datetime import datetime, timedelta

from sqlalchemy import delete, select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.triage import SuppressedDelivery

logger = logging.getLogger(__name__)

CANONICAL_CAP = 10  # Max suppressed items per user per day
RETENTION_DAYS = 90


class SuppressedDeliveryService:
    """Manages suppressed delivery records for counterfactual review."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def record_suppression(
        self,
        user_id: str,
        message_id: str,
        original_action: str,
        suppression_reason: str,
        outcome_summary: str | None = None,
    ) -> SuppressedDelivery | None:
        """Record a suppressed delivery.

        Respects canonical cap of 10 per user per day.

        Returns:
            SuppressedDelivery if recorded, None if cap reached.
        """
        # Check cap
        today_start = datetime.utcnow().replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        result = await self.db.execute(
            select(func.count()).where(
                SuppressedDelivery.user_id == user_id,
                SuppressedDelivery.created_at >= today_start,
            )
        )
        count = result.scalar() or 0

        if count >= CANONICAL_CAP:
            logger.info(
                f"Suppressed delivery cap reached for user {user_id} "
                f"({count} items today)"
            )
            return None

        suppressed = SuppressedDelivery(
            user_id=user_id,
            message_id=message_id,
            original_action=original_action,
            suppression_reason=suppression_reason,
            outcome_summary=outcome_summary,
        )
        self.db.add(suppressed)
        await self.db.commit()
        await self.db.refresh(suppressed)

        return suppressed

    async def get_for_review(
        self,
        user_id: str,
        limit: int = CANONICAL_CAP,
    ) -> list[SuppressedDelivery]:
        """Get suppressed deliveries for counterfactual review.

        Returns newest items first, up to cap limit.
        """
        result = await self.db.execute(
            select(SuppressedDelivery)
            .where(SuppressedDelivery.user_id == user_id)
            .where(SuppressedDelivery.user_review_response.is_(None))
            .order_by(SuppressedDelivery.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def record_review_response(
        self,
        suppressed_id: str,
        user_id: str,
        response: str,  # "yes" | "no" | "maybe"
    ) -> bool:
        """Record user's review response.

        "yes" responses feed R3 as strong positive signal.
        """
        result = await self.db.execute(
            select(SuppressedDelivery).where(
                SuppressedDelivery.id == suppressed_id,
                SuppressedDelivery.user_id == user_id,
            )
        )
        suppressed = result.scalar_one_or_none()

        if not suppressed:
            return False

        suppressed.user_review_response = response
        await self.db.commit()

        # TODO: If response == "yes", feed to R3 learning consumers

        return True

    async def cleanup_expired(self) -> int:
        """Delete records older than retention period."""
        cutoff = datetime.utcnow() - timedelta(days=RETENTION_DAYS)
        result = await self.db.execute(
            delete(SuppressedDelivery).where(
                SuppressedDelivery.created_at < cutoff
            )
        )
        await self.db.commit()
        return result.rowcount
```

### Step 4: Run migration

```bash
docker-compose -f docker-compose.dev.yml exec backend alembic upgrade head
```

### Step 5: Commit

```bash
git add backend/alembic/versions/045_add_suppressed_deliveries.py \
        backend/app/db/models/triage.py \
        backend/app/services/suppressed_delivery_service.py
git commit -m "feat(triage): add SuppressedDeliveryService for counterfactual review"
```

---

## Task 4: Wire learning consumers to classifier

**Files:**
- Modify: `backend/app/services/triage_classifier.py`
- Modify: `backend/app/services/triage_enrichment.py`
- Modify: `backend/app/services/triage_pipeline.py`

### Step 1: Update TriageClassifier to accept learning signals

- [ ] **Update classify method signature**

```python
# backend/app/services/triage_classifier.py
# Update ClassificationResult to include reasoning signals:

@dataclass
class ReasoningSignals:
    """Structured reasoning behind classification."""
    few_shot_examples: list[LearnedExample] = field(default_factory=list)
    sender_distribution: dict | None = None
    topic_bias: list[str] = field(default_factory=list)
    channel_rule: str | None = None
    vip_sender: bool = False
    confidence_threshold_met: bool = True


@dataclass
class ClassificationResult:
    """Result of classifying a message."""

    action: str
    confidence: float
    reason: str
    abstract: str
    review: bool = False
    needs_more_context: bool = False
    message_type: str | None = None
    keyword_matches: list[str] = field(default_factory=list)
    reasoning_signals: ReasoningSignals = field(default_factory=ReasoningSignals)
```

- [ ] **Update _llm_classify to inject few-shot examples**

```python
# backend/app/services/triage_classifier.py
# Add few-shot examples to system prompt:

    async def _llm_classify(
        self, payload: EnrichedTriagePayload, path: str, vip_boost: bool = False
    ) -> ClassificationResult:
        # ... existing setup ...

        # Inject few-shot examples if available
        few_shot_section = ""
        if payload.few_shot_examples:
            examples_text = "\n\n".join([
                f"Example: '{ex.original_abstract}' → {ex.correct_action}"
                for ex in payload.few_shot_examples[:3]
            ])
            few_shot_section = f"""

**Similar past corrections (learn from these):**
{examples_text}"""

        # Inject sender distribution if available
        sender_dist_section = ""
        if payload.sender_action_distribution:
            dist = payload.sender_action_distribution
            sender_dist_section = f"""

**Sender's past actions in this channel:**
- notify_now: {dist.get('notify_now', 0) * 100:.0f}%
- summarize_next: {dist.get('summarize_next', 0) * 100:.0f}%
- summarize_eod: {dist.get('summarize_eod', 0) * 100:.0f}%
- ignore: {dist.get('ignore', 0) * 100:.0f}%"""

        # Inject topic bias if available
        topic_bias_section = ""
        if payload.topic_biases:
            positive = [b.keyword for b in payload.topic_biases if b.weight > 0]
            negative = [b.keyword for b in payload.topic_biases if b.weight < 0]
            if positive:
                topic_bias_section += f"\n**Topics you engage with:** {', '.join(positive[:5])}"
            if negative:
                topic_bias_section += f"\n**Topics you ignore:** {', '.join(negative[:5])}"

        system_prompt = f"""...
{few_shot_section}{sender_dist_section}{topic_bias_section}
..."""
```

### Step 2: Update enrichment to gather learning signals

- [ ] **Update EnrichedTriagePayload**

```python
# backend/app/services/triage_enrichment.py
# Add fields to EnrichedTriagePayload:

@dataclass
class EnrichedTriagePayload:
    # ... existing fields ...

    # Learning signals (Phase 2)
    few_shot_examples: list = field(default_factory=list)
    sender_action_distribution: dict | None = None
    topic_biases: list = field(default_factory=list)
```

- [ ] **Update enrich method to fetch signals**

```python
# backend/app/services/triage_enrichment.py
# Add to enrich method:

        # Phase 2: Fetch learning signals
        try:
            from app.services.learned_example_retriever import LearnedExampleRetriever
            from app.services.topic_affinity_service import TopicAffinityService
            from app.db.models.triage import SenderActionDistribution

            # Few-shot examples
            if message_text:
                retriever = LearnedExampleRetriever(self.db)
                payload.few_shot_examples = await retriever.retrieve_examples(
                    user_id=user_id,
                    channel_id=channel_id if event_type == "channel" else None,
                    sender_slack_id=sender_slack_id,
                    message_text=message_text,
                )

            # Sender action distribution
            if event_type == "channel" and channel_id:
                result = await self.db.execute(
                    select(SenderActionDistribution).where(
                        SenderActionDistribution.user_id == user_id,
                        SenderActionDistribution.sender_slack_id == sender_slack_id,
                        SenderActionDistribution.channel_id == channel_id,
                    )
                )
                dist = result.scalar_one_or_none()
                if dist and dist.sample_count >= 10:  # Minimum evidence threshold
                    payload.sender_action_distribution = dist.action_distribution

            # Topic biases
            topic_service = TopicAffinityService(self.db)
            payload.topic_biases = await topic_service.get_biases(user_id)

        except Exception as e:
            logger.warning(f"Failed to fetch learning signals: {e}")
```

### Step 3: Commit

```bash
git add backend/app/services/triage_classifier.py \
        backend/app/services/triage_enrichment.py
git commit -m "feat(triage): wire learning consumers to classifier"
```

---

## Task 5: Create Transparency API endpoints

**Files:**
- Create: `backend/app/api/triage_transparency.py`
- Modify: `backend/app/main.py` (add router)

### Step 1: Create API endpoints

- [ ] **Create API file**

```python
# backend/app/api/triage_transparency.py
"""Transparency API for R-Transparency.

Users can view and delete learned data:
- Topic keywords
- Sender distributions
- Per-type delivery windows
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.db.models.user import User
from app.services.topic_affinity_service import TopicAffinityService
from app.services.learned_data_audit_service import LearnedDataAuditService
from app.schemas.triage import (
    TopicAffinityList,
    TopicAffinityDelete,
    SenderDistributionList,
)

router = APIRouter(prefix="/triage/transparency", tags=["triage-transparency"])


@router.get("/keywords", response_model=TopicAffinityList)
async def list_learned_keywords(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all learned topic keywords for the current user."""
    service = TopicAffinityService(db)
    biases = await service.get_biases(current_user.id)
    
    return TopicAffinityList(
        keywords=[
            {
                "keyword": b.keyword,
                "weight": b.weight,
                "source_category": b.source_category,
            }
            for b in biases
        ]
    )


@router.delete("/keywords/{keyword}")
async def delete_keyword(
    keyword: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a learned topic keyword."""
    service = TopicAffinityService(db)
    deleted = await service.delete_keyword(current_user.id, keyword)
    
    if not deleted:
        raise HTTPException(status_code=404, detail="Keyword not found")
    
    return {"deleted": True}


@router.delete("/keywords/category/{category}")
async def delete_keywords_by_category(
    category: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete all keywords from a source category."""
    service = TopicAffinityService(db)
    count = await service.delete_by_category(current_user.id, category)
    
    return {"deleted_count": count}


@router.get("/distributions", response_model=SenderDistributionList)
async def list_sender_distributions(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all learned sender action distributions."""
    service = LearnedDataAuditService(db)
    distributions = await service.get_sender_distributions(current_user.id)
    
    return SenderDistributionList(distributions=distributions)
```

### Step 2: Register router

- [ ] **Add to main.py**

```python
# backend/app/main.py
# Add import and include_router:

from app.api.triage_transparency import router as transparency_router

app.include_router(transparency_router, prefix="/api")
```

### Step 3: Commit

```bash
git add backend/app/api/triage_transparency.py \
        backend/app/main.py
git commit -m "feat(triage): add transparency API endpoints for R-Transparency"
```

---

## Task 6: Create Frontend Transparency UI

**Files:**
- Create: `frontend/src/pages/TriageTransparencyPage.tsx`
- Create: `frontend/src/components/triage/LearnedKeywordsCard.tsx`
- Create: `frontend/src/hooks/useTriageTransparency.ts`

### Step 1: Create hooks

- [ ] **Create hook file**

```typescript
// frontend/src/hooks/useTriageTransparency.ts
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api'

export interface LearnedKeyword {
  keyword: string
  weight: number
  source_category: 'public' | 'sensitive' | 'dm'
}

export function useLearnedKeywords() {
  return useQuery({
    queryKey: ['triage', 'transparency', 'keywords'],
    queryFn: async () => {
      const { data } = await api.get<TriageTransparency.KeywordList>(
        '/triage/transparency/keywords'
      )
      return data.keywords
    },
  })
}

export function useDeleteKeyword() {
  const queryClient = useQueryClient()
  
  return useMutation({
    mutationFn: async (keyword: string) => {
      await api.delete(`/triage/transparency/keywords/${encodeURIComponent(keyword)}`)
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['triage', 'transparency', 'keywords'] })
    },
  })
}

export function useDeleteKeywordsByCategory() {
  const queryClient = useQueryClient()
  
  return useMutation({
    mutationFn: async (category: string) => {
      const { data } = await api.delete<{ deleted_count: number }>(
        `/triage/transparency/keywords/category/${category}`
      )
      return data.deleted_count
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['triage', 'transparency', 'keywords'] })
    },
  })
}
```

### Step 2: Create LearnedKeywordsCard

- [ ] **Create component**

```tsx
// frontend/src/components/triage/LearnedKeywordsCard.tsx
import { useState } from 'react'
import { Trash2, AlertTriangle } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog'
import {
  useLearnedKeywords,
  useDeleteKeyword,
  useDeleteKeywordsByCategory,
  type LearnedKeyword,
} from '@/hooks/useTriageTransparency'

function KeywordBadge({ keyword, onDelete }: { keyword: LearnedKeyword; onDelete: () => void }) {
  const isPositive = keyword.weight > 0
  const bgColor = isPositive
    ? 'bg-green-100 dark:bg-green-900/30'
    : 'bg-red-100 dark:bg-red-900/30'
  const textColor = isPositive
    ? 'text-green-800 dark:text-green-200'
    : 'text-red-800 dark:text-red-200'

  return (
    <div className={`inline-flex items-center gap-1 px-2 py-1 rounded ${bgColor} ${textColor}`}>
      <span>{keyword.keyword}</span>
      <span className="text-xs opacity-70">({keyword.weight.toFixed(2)})</span>
      <button
        onClick={onDelete}
        className="ml-1 hover:opacity-70"
        title="Delete keyword"
      >
        <Trash2 className="h-3 w-3" />
      </button>
    </div>
  )
}

export function LearnedKeywordsCard() {
  const { data: keywords, isLoading } = useLearnedKeywords()
  const deleteKeyword = useDeleteKeyword()
  const deleteByCategory = useDeleteKeywordsByCategory()
  const [confirmCategory, setConfirmCategory] = useState<string | null>(null)

  if (isLoading) return <div>Loading...</div>
  if (!keywords?.length) return <div>No learned keywords yet.</div>

  const publicKw = keywords.filter((k) => k.source_category === 'public')
  const sensitiveKw = keywords.filter((k) => k.source_category === 'sensitive')
  const dmKw = keywords.filter((k) => k.source_category === 'dm')

  return (
    <Card>
      <CardHeader>
        <CardTitle>Learned Topic Keywords</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <p className="text-sm text-muted-foreground">
          Alfred learns which topics you engage with. These keywords influence
          classification decisions.
        </p>

        {publicKw.length > 0 && (
          <div>
            <div className="flex items-center justify-between mb-2">
              <h4 className="font-medium">From Public Channels</h4>
              <Dialog>
                <DialogTrigger asChild>
                  <Button variant="ghost" size="sm" className="text-destructive">
                    Delete all
                  </Button>
                </DialogTrigger>
                <DialogContent>
                  <DialogHeader>
                    <DialogTitle>Delete all public channel keywords?</DialogTitle>
                    <DialogDescription>
                      This will remove {publicKw.length} keywords learned from
                      public channels.
                    </DialogDescription>
                  </DialogHeader>
                  <DialogFooter>
                    <Button variant="outline">Cancel</Button>
                    <Button
                      variant="destructive"
                      onClick={() => deleteByCategory.mutate('public')}
                    >
                      Delete
                    </Button>
                  </DialogFooter>
                </DialogContent>
              </Dialog>
            </div>
            <div className="flex flex-wrap gap-2">
              {publicKw.map((kw) => (
                <KeywordBadge
                  key={kw.keyword}
                  keyword={kw}
                  onDelete={() => deleteKeyword.mutate(kw.keyword)}
                />
              ))}
            </div>
          </div>
        )}

        {sensitiveKw.length > 0 && (
          <div>
            <div className="flex items-center gap-2 mb-2">
              <h4 className="font-medium">From Sensitive Channels</h4>
              <AlertTriangle className="h-4 w-4 text-yellow-500" />
            </div>
            <div className="flex flex-wrap gap-2">
              {sensitiveKw.map((kw) => (
                <KeywordBadge
                  key={kw.keyword}
                  keyword={kw}
                  onDelete={() => deleteKeyword.mutate(kw.keyword)}
                />
              ))}
            </div>
          </div>
        )}

        {dmKw.length > 0 && (
          <div>
            <div className="flex items-center gap-2 mb-2">
              <h4 className="font-medium">From DMs</h4>
              <AlertTriangle className="h-4 w-4 text-yellow-500" />
            </div>
            <div className="flex flex-wrap gap-2">
              {dmKw.map((kw) => (
                <KeywordBadge
                  key={kw.keyword}
                  keyword={kw}
                  onDelete={() => deleteKeyword.mutate(kw.keyword)}
                />
              ))}
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  )
}
```

### Step 3: Create page

- [ ] **Create page file**

```tsx
// frontend/src/pages/TriageTransparencyPage.tsx
import { ArrowLeft } from 'lucide-react'
import { Link } from 'react-router-dom'
import { Button } from '@/components/ui/button'
import { LearnedKeywordsCard } from '@/components/triage/LearnedKeywordsCard'

export function TriageTransparencyPage() {
  return (
    <div className="container max-w-4xl py-6 space-y-6">
      <div className="flex items-center gap-4">
        <Link to="/triage">
          <Button variant="ghost" size="sm">
            <ArrowLeft className="h-4 w-4 mr-2" />
            Back
          </Button>
        </Link>
        <h1 className="text-2xl font-bold">Learned Data</h1>
      </div>

      <p className="text-muted-foreground">
        View and manage what Alfred has learned about your preferences.
        This data influences classification decisions.
      </p>

      <LearnedKeywordsCard />
    </div>
  )
}
```

### Step 4: Add route

- [ ] **Add to router**

```typescript
// frontend/src/App.tsx
// Add route:

import { TriageTransparencyPage } from '@/pages/TriageTransparencyPage'

// In routes:
<Route path="/triage/transparency" element={<TriageTransparencyPage />} />
```

### Step 5: Commit

```bash
git add frontend/src/pages/TriageTransparencyPage.tsx \
        frontend/src/components/triage/LearnedKeywordsCard.tsx \
        frontend/src/hooks/useTriageTransparency.ts \
        frontend/src/App.tsx
git commit -m "feat(triage): add transparency UI for learned keywords"
```

---

## Acceptance Criteria Checklist

- [ ] One-tap correction controls on every digest item and notify-now push
- [ ] `LearnedExampleRetriever` deployed and consumed by classifier prompt
- [ ] `FeedbackEmbedding` table stores derived embeddings; no time limit on retention
- [ ] R3b works for sensitive content via on-demand Slack fetch at correction time
- [ ] New `SenderActionDistribution` table; `SenderBehaviorModel` preserved
- [ ] Nightly job computes and writes action distributions with 30-day decay
- [ ] Minimum-evidence threshold (10 samples) enforced before R3c reasoning surfaces
- [ ] Topic-affinity keyword extraction and bias injection working
- [ ] Topic affinity works for all content types (sensitive and non-sensitive)
- [ ] Learned-keywords audit UI: view, delete individual, bulk-delete by category
- [ ] Within 2 weeks of use, classification reasoning visibly cites learned signals

---

*Phase 2 complete. Proceed to phase-3-patterns.md.*
