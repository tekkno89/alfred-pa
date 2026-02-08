"""Repository for User model operations."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import User
from app.db.repositories.base import BaseRepository


class UserRepository(BaseRepository[User]):
    """Repository for User CRUD operations."""

    def __init__(self, db: AsyncSession):
        super().__init__(User, db)

    async def get_by_email(self, email: str) -> User | None:
        """Get a user by email address."""
        result = await self.db.execute(
            select(User).where(User.email == email)
        )
        return result.scalar_one_or_none()

    async def get_by_slack_id(self, slack_user_id: str) -> User | None:
        """Get a user by their Slack user ID."""
        result = await self.db.execute(
            select(User).where(User.slack_user_id == slack_user_id)
        )
        return result.scalar_one_or_none()

    async def create_user(
        self, email: str, password_hash: str | None = None
    ) -> User:
        """Create a new user."""
        user = User(email=email, password_hash=password_hash)
        return await self.create(user)

    async def link_slack(self, user_id: str, slack_user_id: str) -> User:
        """
        Link a Slack user ID to a user account.

        Args:
            user_id: The user's ID
            slack_user_id: The Slack user ID to link

        Returns:
            The updated user

        Raises:
            ValueError: If user not found or Slack ID already linked
        """
        user = await self.get(user_id)
        if not user:
            raise ValueError("User not found")

        # Check if Slack ID is already linked to another user
        existing = await self.get_by_slack_id(slack_user_id)
        if existing and existing.id != user_id:
            raise ValueError("Slack account already linked to another user")

        return await self.update(user, slack_user_id=slack_user_id)

    async def unlink_slack(self, user_id: str) -> User:
        """
        Unlink a Slack account from a user.

        Args:
            user_id: The user's ID

        Returns:
            The updated user

        Raises:
            ValueError: If user not found
        """
        user = await self.get(user_id)
        if not user:
            raise ValueError("User not found")

        return await self.update(user, slack_user_id=None)
