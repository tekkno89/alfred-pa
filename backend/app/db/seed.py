"""
Database seeding script for development.

Run with: python -m app.db.seed
"""
import asyncio
from uuid import uuid4

from passlib.hash import bcrypt
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import async_session_maker
from app.db.models import User, Session, Message


async def seed_database() -> None:
    """Seed the database with development data."""
    async with async_session_maker() as session:
        await seed_users(session)
        await seed_sessions(session)
        await session.commit()
        print("Database seeded successfully!")


async def seed_users(session: AsyncSession) -> None:
    """Seed test users."""
    # Check if admin user exists
    from sqlalchemy import select

    result = await session.execute(select(User).where(User.email == "admin@alfred.local"))
    if result.scalar_one_or_none():
        print("Admin user already exists, skipping user seed")
        return

    admin_user = User(
        id=str(uuid4()),
        email="admin@alfred.local",
        password_hash=bcrypt.hash("password"),
    )
    session.add(admin_user)
    print(f"Created admin user: {admin_user.email}")


async def seed_sessions(session: AsyncSession) -> None:
    """Seed test sessions with messages."""
    from sqlalchemy import select

    result = await session.execute(select(User).where(User.email == "admin@alfred.local"))
    admin_user = result.scalar_one_or_none()

    if not admin_user:
        print("No admin user found, skipping session seed")
        return

    # Check if sessions exist
    result = await session.execute(select(Session).where(Session.user_id == admin_user.id))
    if result.first():
        print("Sessions already exist, skipping session seed")
        return

    # Create a sample webapp session
    webapp_session = Session(
        id=str(uuid4()),
        user_id=admin_user.id,
        title="Welcome conversation",
        source="webapp",
    )
    session.add(webapp_session)

    # Add sample messages
    messages = [
        Message(
            id=str(uuid4()),
            session_id=webapp_session.id,
            role="user",
            content="Hello Alfred!",
        ),
        Message(
            id=str(uuid4()),
            session_id=webapp_session.id,
            role="assistant",
            content="Hello! I'm Alfred, your personal AI assistant. How can I help you today?",
        ),
    ]
    session.add_all(messages)
    print(f"Created sample session: {webapp_session.title}")


if __name__ == "__main__":
    asyncio.run(seed_database())
