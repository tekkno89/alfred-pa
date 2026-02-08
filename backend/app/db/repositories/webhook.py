"""Repository for Webhook operations."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import WebhookSubscription
from app.db.repositories.base import BaseRepository


class WebhookRepository(BaseRepository[WebhookSubscription]):
    """Repository for WebhookSubscription CRUD operations."""

    def __init__(self, db: AsyncSession):
        super().__init__(WebhookSubscription, db)

    async def get_by_user_id(self, user_id: str) -> list[WebhookSubscription]:
        """Get all webhook subscriptions for a user."""
        result = await self.db.execute(
            select(WebhookSubscription).where(WebhookSubscription.user_id == user_id)
        )
        return list(result.scalars().all())

    async def get_enabled_for_event(
        self, user_id: str, event_type: str
    ) -> list[WebhookSubscription]:
        """Get all enabled webhooks for a user that subscribe to an event type."""
        # We need to check if event_type is in the JSON array
        # Using PostgreSQL JSON containment operator
        result = await self.db.execute(
            select(WebhookSubscription)
            .where(WebhookSubscription.user_id == user_id)
            .where(WebhookSubscription.enabled == True)  # noqa: E712
        )
        webhooks = list(result.scalars().all())
        # Filter by event type in Python (JSON array containment varies by DB)
        return [w for w in webhooks if event_type in w.event_types]

    async def create_webhook(
        self,
        user_id: str,
        name: str,
        url: str,
        event_types: list[str],
    ) -> WebhookSubscription:
        """Create a new webhook subscription."""
        webhook = WebhookSubscription(
            user_id=user_id,
            name=name,
            url=url,
            event_types=event_types,
        )
        return await self.create(webhook)
