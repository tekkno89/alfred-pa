import asyncio
from collections.abc import AsyncGenerator, Generator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    create_async_engine,
    async_sessionmaker,
)
from sqlalchemy.pool import NullPool

from app.main import app
from app.db.base import Base
from app.api.deps import get_db


# Test database URL (use a separate test database)
TEST_DATABASE_URL = "postgresql+asyncpg://alfred:alfred@localhost:5432/alfred_test"

# Create engine with NullPool to avoid connection reuse issues
test_engine = create_async_engine(
    TEST_DATABASE_URL,
    echo=False,
    poolclass=NullPool,  # Don't pool connections - each test gets a fresh one
)

# Session factory
TestSessionLocal = async_sessionmaker(
    test_engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


@pytest.fixture(scope="session")
def event_loop() -> Generator[asyncio.AbstractEventLoop, None, None]:
    """Create an event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def setup_database():
    """Set up the database once for all tests."""
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield
    await test_engine.dispose()


@pytest_asyncio.fixture
async def db_session(setup_database) -> AsyncGenerator[AsyncSession, None]:
    """Create a fresh database session for each test."""
    async with TestSessionLocal() as session:
        yield session

    # Clean up after each test
    async with TestSessionLocal() as cleanup_session:
        for table in reversed(Base.metadata.sorted_tables):
            await cleanup_session.execute(table.delete())
        await cleanup_session.commit()


@pytest_asyncio.fixture
async def client(setup_database) -> AsyncGenerator[AsyncClient, None]:
    """Create a test client with proper database sessions."""

    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        async with TestSessionLocal() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_db] = override_get_db

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as ac:
        yield ac

    app.dependency_overrides.clear()
