"""Few-shot example retrieval from past corrections.

R3b: Retrieve top-K semantically similar past corrections and inject
as few-shot exemplars in the classifier prompt.
"""

import logging
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.embeddings import get_embedding_provider
from app.db.models.triage import (
    FeedbackEmbedding,
    TriageClassification,
    TriageFeedback,
)

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
        embedding_provider = get_embedding_provider()
        embedding = await embedding_provider.embed_text(message_text)

        distance_expr = FeedbackEmbedding.embedding_vector.cosine_distance(embedding)
        query = (
            select(
                FeedbackEmbedding,
                TriageFeedback,
                TriageClassification,
                (1 - distance_expr).label("similarity"),
            )
            .join(
                TriageFeedback,
                FeedbackEmbedding.triage_feedback_id == TriageFeedback.id,
            )
            .join(
                TriageClassification,
                TriageFeedback.classification_id == TriageClassification.id,
            )
            .where(TriageFeedback.user_id == user_id)
            .where(TriageFeedback.was_correct.is_(False))
            .where(TriageFeedback.correct_action.isnot(None))
            .order_by(distance_expr)
            .limit(top_k)
        )

        if channel_id:
            query = query.where(TriageClassification.channel_id == channel_id)
        if sender_slack_id:
            query = query.where(
                TriageClassification.sender_slack_id == sender_slack_id
            )

        result = await self.db.execute(query)
        rows = result.all()

        examples = []
        for row in rows:
            feedback_emb, feedback, classification, similarity = row
            examples.append(
                LearnedExample(
                    original_abstract=classification.abstract or "Message",
                    correct_action=feedback.correct_action or "summarize_next",
                    feedback_reason=feedback.feedback_text,
                    similarity=float(similarity),
                )
            )

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
