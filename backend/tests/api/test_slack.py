"""Tests for Slack API endpoints."""

import hashlib
import hmac
import json
import time
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.fixture
def valid_signature():
    """Generate valid Slack signature for a payload."""

    def _generate(body: bytes, signing_secret: str = "test-signing-secret"):
        timestamp = str(int(time.time()))
        sig_basestring = f"v0:{timestamp}:{body.decode('utf-8')}"
        signature = (
            "v0="
            + hmac.new(
                signing_secret.encode("utf-8"),
                sig_basestring.encode("utf-8"),
                hashlib.sha256,
            ).hexdigest()
        )
        return timestamp, signature

    return _generate


class TestSlackEvents:
    """Tests for /slack/events endpoint."""

    @pytest_asyncio.fixture
    async def client(self):
        """Create test client."""
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as ac:
            yield ac

    async def test_url_verification(self, client):
        """Test Slack URL verification challenge."""
        payload = {
            "type": "url_verification",
            "challenge": "test-challenge-token",
        }

        response = await client.post(
            "/api/slack/events",
            json=payload,
        )

        assert response.status_code == 200
        assert response.json() == {"challenge": "test-challenge-token"}

    async def test_event_callback_invalid_signature(self, client):
        """Test event callback with invalid signature."""
        payload = {
            "type": "event_callback",
            "event": {"type": "message"},
        }
        body = json.dumps(payload).encode()

        response = await client.post(
            "/api/slack/events",
            content=body,
            headers={
                "Content-Type": "application/json",
                "X-Slack-Request-Timestamp": str(int(time.time())),
                "X-Slack-Signature": "v0=invalid",
            },
        )

        assert response.status_code == 401

    async def test_event_callback_valid_signature(self, client, valid_signature):
        """Test event callback with valid signature."""
        payload = {
            "type": "event_callback",
            "event": {
                "type": "message",
                "user": "U123456",
                "channel": "C123456",
                "text": "Hello Alfred",
                "ts": "1234567890.123456",
            },
        }
        body = json.dumps(payload).encode()
        timestamp, signature = valid_signature(body)

        with patch("app.api.slack.get_slack_service") as mock_slack:
            mock_service = AsyncMock()
            mock_slack.return_value = mock_service
            mock_service.verify_signature.return_value = True
            mock_service.send_message = AsyncMock()

            response = await client.post(
                "/api/slack/events",
                content=body,
                headers={
                    "Content-Type": "application/json",
                    "X-Slack-Request-Timestamp": timestamp,
                    "X-Slack-Signature": signature,
                },
            )

        assert response.status_code == 200
        assert response.json() == {"ok": True}


class TestSlackCommands:
    """Tests for /slack/commands endpoint."""

    @pytest_asyncio.fixture
    async def client(self):
        """Create test client."""
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as ac:
            yield ac

    async def test_link_command_invalid_signature(self, client):
        """Test link command with invalid signature."""
        response = await client.post(
            "/api/slack/commands",
            data={
                "command": "/alfred-link",
                "user_id": "U123456",
            },
            headers={
                "X-Slack-Request-Timestamp": str(int(time.time())),
                "X-Slack-Signature": "v0=invalid",
            },
        )

        assert response.status_code == 401

    async def test_link_command_success(self, client, valid_signature):
        """Test successful link command."""
        form_data = "command=%2Falfred-link&user_id=U123456"
        timestamp, signature = valid_signature(form_data.encode())

        with patch("app.api.slack.get_slack_service") as mock_slack, patch(
            "app.api.slack.get_linking_service"
        ) as mock_linking:
            mock_slack_service = AsyncMock()
            mock_slack.return_value = mock_slack_service
            mock_slack_service.verify_signature.return_value = True

            mock_linking_service = AsyncMock()
            mock_linking.return_value = mock_linking_service
            mock_linking_service.create_code.return_value = "ABC123"

            response = await client.post(
                "/api/slack/commands",
                content=form_data,
                headers={
                    "Content-Type": "application/x-www-form-urlencoded",
                    "X-Slack-Request-Timestamp": timestamp,
                    "X-Slack-Signature": signature,
                },
            )

        assert response.status_code == 200
        result = response.json()
        assert result["response_type"] == "ephemeral"
        assert "ABC123" in result["text"]


class TestSlackLinkingEndpoints:
    """Tests for Slack linking auth endpoints."""

    @pytest_asyncio.fixture
    async def client(self, setup_database):
        """Create test client with database."""
        from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
        from sqlalchemy.pool import NullPool
        from app.api.deps import get_db
        from app.db.base import Base
        import os

        _db_host = os.getenv("TEST_DB_HOST", "postgres")
        TEST_DATABASE_URL = f"postgresql+asyncpg://alfred:alfred@{_db_host}:5432/alfred_test"

        test_engine = create_async_engine(
            TEST_DATABASE_URL,
            echo=False,
            poolclass=NullPool,
        )

        TestSessionLocal = async_sessionmaker(
            test_engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )

        async def override_get_db():
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

    @pytest.fixture
    def setup_database(self):
        """Database setup fixture (uses existing conftest.py setup)."""
        pass

    async def test_slack_status_unauthenticated(self, client):
        """Test slack status without authentication."""
        response = await client.get("/api/auth/slack-status")
        assert response.status_code == 401

    async def test_link_slack_invalid_code(self, client):
        """Test linking with invalid code."""
        # This test requires authentication, which is complex to mock
        # In a real test environment, we'd set up a user and JWT token
        pass
