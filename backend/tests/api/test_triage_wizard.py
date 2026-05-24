"""Tests for triage wizard API endpoints."""

import json
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.dashboard import UserFeatureAccess
from tests.conftest import auth_headers
from tests.factories import UserFactory


@pytest.fixture
async def test_user(db_session: AsyncSession):
    """Create a test user with triage feature access."""
    user = UserFactory()
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    access = UserFeatureAccess(
        user_id=user.id,
        feature_key="card:triage",
        enabled=True,
        granted_by=user.id,
    )
    db_session.add(access)
    await db_session.commit()

    return user


class TestGenerateGoals:
    """Tests for generate_goals endpoint."""

    async def test_generate_goals(self, client: AsyncClient, test_user):
        """Generate goals based on role."""
        mock_llm = AsyncMock()
        mock_llm.generate.return_value = json.dumps({
            "goals": [
                {"id": "incidents", "label": "Stay on top of production incidents"},
                {"id": "noise", "label": "Reduce noise from automated messages"},
                {"id": "reviews", "label": "Never miss code review requests"},
            ]
        })

        with patch("app.api.triage_wizard.get_llm_provider") as mock_get_llm:
            mock_get_llm.return_value = mock_llm

            response = await client.post(
                "/api/triage/wizard/generate-goals",
                json={"role": "Software Engineer"},
                headers=auth_headers(test_user),
            )

        assert response.status_code == 200
        data = response.json()
        assert "goals" in data
        assert len(data["goals"]) == 3
        assert data["goals"][0]["id"] == "incidents"
        assert data["goals"][0]["label"] == "Stay on top of production incidents"

    async def test_generate_goals_handles_invalid_json(
        self, client: AsyncClient, test_user
    ):
        """Test that invalid JSON from LLM returns fallback goals."""
        mock_llm = AsyncMock()
        mock_llm.generate.return_value = "not valid json {{{"

        with patch("app.api.triage_wizard.get_llm_provider") as mock_get_llm:
            mock_get_llm.return_value = mock_llm

            response = await client.post(
                "/api/triage/wizard/generate-goals",
                json={"role": "Software Engineer"},
                headers=auth_headers(test_user),
            )

        assert response.status_code == 200
        data = response.json()
        assert "goals" in data
        assert len(data["goals"]) == 5
        assert data["goals"][0]["id"] == "incidents"

    async def test_generate_goals_strips_markdown(
        self, client: AsyncClient, test_user
    ):
        """Test that markdown code blocks are stripped from LLM response."""
        mock_llm = AsyncMock()
        mock_llm.generate.return_value = """```json
{"goals": [{"id": "test", "label": "Test goal"}]}
```"""

        with patch("app.api.triage_wizard.get_llm_provider") as mock_get_llm:
            mock_get_llm.return_value = mock_llm

            response = await client.post(
                "/api/triage/wizard/generate-goals",
                json={"role": "Software Engineer"},
                headers=auth_headers(test_user),
            )

        assert response.status_code == 200
        data = response.json()
        assert len(data["goals"]) == 1
        assert data["goals"][0]["id"] == "test"

    async def test_generate_goals_role_too_short(
        self, client: AsyncClient, test_user
    ):
        """Test that role must be at least 3 characters."""
        response = await client.post(
            "/api/triage/wizard/generate-goals",
            json={"role": "ab"},
            headers=auth_headers(test_user),
        )

        assert response.status_code == 422

    async def test_generate_goals_role_too_long(
        self, client: AsyncClient, test_user
    ):
        """Test that role must be at most 500 characters."""
        response = await client.post(
            "/api/triage/wizard/generate-goals",
            json={"role": "a" * 501},
            headers=auth_headers(test_user),
        )

        assert response.status_code == 422


class TestGenerateQuestions:
    """Tests for generate_questions endpoint."""

    async def test_generate_questions(self, client: AsyncClient, test_user):
        """Generate questions based on role and goals."""
        mock_llm = AsyncMock()
        mock_llm.generate.return_value = json.dumps({
            "questions": [
                {
                    "question": "When a production incident is reported, how should you be notified?",
                    "options": ["Immediately (P0)", "In next digest (P1)", "End of day (P2)"],
                    "context": "incident_handling"
                },
                {
                    "question": "How should direct mentions be handled?",
                    "options": ["Notify immediately", "Include in digest"],
                    "context": "mentions"
                },
            ]
        })

        with patch("app.api.triage_wizard.get_llm_provider") as mock_get_llm:
            mock_get_llm.return_value = mock_llm

            response = await client.post(
                "/api/triage/wizard/generate-questions",
                json={"role": "Software Engineer", "goals": ["Reduce interruptions", "Stay informed"]},
                headers=auth_headers(test_user),
            )

        assert response.status_code == 200
        data = response.json()
        assert "questions" in data
        assert len(data["questions"]) >= 1

    async def test_generate_questions_handles_invalid_json(
        self, client: AsyncClient, test_user
    ):
        """Test that invalid JSON from LLM returns empty questions list."""
        mock_llm = AsyncMock()
        mock_llm.generate.return_value = "not valid json {{{"

        with patch("app.api.triage_wizard.get_llm_provider") as mock_get_llm:
            mock_get_llm.return_value = mock_llm

            response = await client.post(
                "/api/triage/wizard/generate-questions",
                json={"role": "Software Engineer"},
                headers=auth_headers(test_user),
            )

        assert response.status_code == 200
        assert response.json()["questions"] == []

    async def test_generate_questions_strips_markdown(
        self, client: AsyncClient, test_user
    ):
        """Test that markdown code blocks are stripped from LLM response."""
        mock_llm = AsyncMock()
        mock_llm.generate.return_value = """```json
{"questions": [{"question": "Test?", "options": ["A", "B"], "context": "test"}]}
```"""

        with patch("app.api.triage_wizard.get_llm_provider") as mock_get_llm:
            mock_get_llm.return_value = mock_llm

            response = await client.post(
                "/api/triage/wizard/generate-questions",
                json={"role": "Software Engineer"},
                headers=auth_headers(test_user),
            )

        assert response.status_code == 200
        data = response.json()
        assert len(data["questions"]) == 1


class TestGenerateDefinitions:
    """Tests for generate_definitions endpoint."""

    async def test_generate_definitions(self, client: AsyncClient, test_user):
        """Generate priority definitions from user responses."""
        mock_llm = AsyncMock()
        mock_llm.generate.return_value = json.dumps({
            "p0_definition": "Production incidents and critical bugs",
            "p1_definition": "Code reviews and time-sensitive requests",
            "p2_definition": "FYI messages and updates",
            "p3_definition": "Low priority items",
            "suggested_message_types": [
                {"type_name": "Incidents", "type_definition": "Production issues", "confidence": 0.9},
                {"type_name": "Reviews", "type_definition": "Code reviews", "confidence": 0.8},
            ]
        })

        with patch("app.api.triage_wizard.get_llm_provider") as mock_get_llm:
            mock_get_llm.return_value = mock_llm

            response = await client.post(
                "/api/triage/wizard/generate-definitions",
                json={
                    "role": "Software Engineer",
                    "goals": ["Reduce interruptions"],
                    "question_responses": {
                        "incident_handling": "Immediately",
                        "mentions": "Include in digest"
                    },
                    "message_types": []
                },
                headers=auth_headers(test_user),
            )

        assert response.status_code == 200
        data = response.json()
        assert "p0_definition" in data
        assert "p1_definition" in data
        assert "p2_definition" in data
        assert "p3_definition" in data
        assert "suggested_message_types" in data

    async def test_generate_definitions_handles_invalid_json(
        self, client: AsyncClient, test_user
    ):
        """Test that invalid JSON returns default definitions."""
        mock_llm = AsyncMock()
        mock_llm.generate.return_value = "not valid json {{{"

        with patch("app.api.triage_wizard.get_llm_provider") as mock_get_llm:
            mock_get_llm.return_value = mock_llm

            response = await client.post(
                "/api/triage/wizard/generate-definitions",
                json={
                    "role": "Software Engineer",
                    "goals": [],
                    "question_responses": {},
                    "message_types": []
                },
                headers=auth_headers(test_user),
            )

        assert response.status_code == 200
        data = response.json()
        assert "p0_definition" in data
        assert "Urgent items" in data["p0_definition"]

    async def test_generate_definitions_with_example_messages(
        self, client: AsyncClient, test_user
    ):
        """Test that example messages are included in the prompt."""
        mock_llm = AsyncMock()
        mock_llm.generate.return_value = json.dumps({
            "p0_definition": "Critical",
            "p1_definition": "Important",
            "p2_definition": "Later",
            "p3_definition": "Low",
            "suggested_message_types": []
        })

        with patch("app.api.triage_wizard.get_llm_provider") as mock_get_llm:
            mock_get_llm.return_value = mock_llm

            response = await client.post(
                "/api/triage/wizard/generate-definitions",
                json={
                    "role": "Software Engineer",
                    "goals": ["Reduce interruptions"],
                    "question_responses": {"q1": "a1"},
                    "message_types": [
                        {"type_name": "Incidents", "type_definition": "Production issues"}
                    ],
                    "example_messages": [
                        {"text": "PROD IS DOWN", "priority": "P0"}
                    ]
                },
                headers=auth_headers(test_user),
            )

        assert response.status_code == 200


class TestFetchMessages:
    """Tests for fetch_messages endpoint."""

    async def test_fetch_messages_valid_permalink(
        self, client: AsyncClient, test_user
    ):
        """Fetch message from valid Slack permalink."""
        with patch(
            "app.services.slack_user.SlackUserService"
        ) as mock_slack_user_cls, patch(
            "slack_sdk.web.async_client.AsyncWebClient"
        ) as mock_client_cls:
            mock_slack_user = AsyncMock()
            mock_slack_user.get_raw_token.return_value = "xoxb-test-token"
            mock_slack_user_cls.return_value = mock_slack_user

            mock_client = AsyncMock()
            mock_client.conversations_replies.return_value = {
                "ok": True,
                "messages": [
                    {"text": "This is a test message", "user": "Test User"}
                ],
            }
            mock_client_cls.return_value = mock_client

            response = await client.post(
                "/api/triage/wizard/fetch-messages",
                json={
                    "slack_links": [
                        "https://test-workspace.slack.com/archives/C12345/p1234567890000000"
                    ]
                },
                headers=auth_headers(test_user),
            )

        assert response.status_code == 200
        data = response.json()
        assert "messages" in data
        assert len(data["messages"]) >= 1
        assert data["messages"][0]["text"] == "This is a test message"

    async def test_fetch_messages_invalid_permalink(
        self, client: AsyncClient, test_user
    ):
        """Test that invalid permalinks are skipped."""
        with patch(
            "app.services.slack_user.SlackUserService"
        ) as mock_slack_user_cls, patch(
            "slack_sdk.web.async_client.AsyncWebClient"
        ) as mock_client_cls:
            mock_slack_user = AsyncMock()
            mock_slack_user.get_raw_token.return_value = "xoxb-test-token"
            mock_slack_user_cls.return_value = mock_slack_user

            mock_client = AsyncMock()
            mock_client_cls.return_value = mock_client

            response = await client.post(
                "/api/triage/wizard/fetch-messages",
                json={
                    "slack_links": [
                        "https://example.com/not-a-slack-link"
                    ]
                },
                headers=auth_headers(test_user),
            )

        assert response.status_code == 200
        data = response.json()
        assert len(data["messages"]) == 0

    async def test_fetch_messages_slack_error(
        self, client: AsyncClient, test_user
    ):
        """Test that Slack API errors are handled gracefully."""
        with patch(
            "app.services.slack_user.SlackUserService"
        ) as mock_slack_user_cls, patch(
            "slack_sdk.web.async_client.AsyncWebClient"
        ) as mock_client_cls:
            mock_slack_user = AsyncMock()
            mock_slack_user.get_raw_token.return_value = "xoxb-test-token"
            mock_slack_user_cls.return_value = mock_slack_user

            mock_client = AsyncMock()
            mock_client.conversations_replies.side_effect = Exception(
                "Slack API error"
            )
            mock_client_cls.return_value = mock_client

            response = await client.post(
                "/api/triage/wizard/fetch-messages",
                json={
                    "slack_links": [
                        "https://test-workspace.slack.com/archives/C12345/p1234567890000000"
                    ]
                },
                headers=auth_headers(test_user),
            )

        assert response.status_code == 200
        data = response.json()
        assert len(data["messages"]) == 0

    async def test_fetch_messages_limits_to_10(
        self, client: AsyncClient, test_user
    ):
        """Test that only first 10 links are processed."""
        with patch(
            "app.services.slack_user.SlackUserService"
        ) as mock_slack_user_cls, patch(
            "slack_sdk.web.async_client.AsyncWebClient"
        ) as mock_client_cls:
            mock_slack_user = AsyncMock()
            mock_slack_user.get_raw_token.return_value = "xoxb-test-token"
            mock_slack_user_cls.return_value = mock_slack_user

            mock_client = AsyncMock()
            mock_client.conversations_replies.return_value = {
                "ok": True,
                "messages": [{"text": "Test", "user": "User"}],
            }
            mock_client_cls.return_value = mock_client

            links = [
                f"https://test.slack.com/archives/C{i}/p123456789000000{i}"
                for i in range(15)
            ]

            response = await client.post(
                "/api/triage/wizard/fetch-messages",
                json={"slack_links": links},
                headers=auth_headers(test_user),
            )

        assert response.status_code == 200
        assert mock_client.conversations_replies.call_count == 10


class TestAuthentication:
    """Tests for authentication requirements."""

    async def test_generate_goals_requires_auth(self, client: AsyncClient):
        """Test that generate_goals requires authentication."""
        response = await client.post(
            "/api/triage/wizard/generate-goals",
            json={"role": "Software Engineer"},
        )
        assert response.status_code == 401

    async def test_generate_questions_requires_auth(self, client: AsyncClient):
        """Test that generate_questions requires authentication."""
        response = await client.post(
            "/api/triage/wizard/generate-questions",
            json={"role": "Software Engineer"},
        )
        assert response.status_code == 401

    async def test_generate_definitions_requires_auth(self, client: AsyncClient):
        """Test that generate_definitions requires authentication."""
        response = await client.post(
            "/api/triage/wizard/generate-definitions",
            json={
                "role": "Software Engineer",
                "goals": [],
                "question_responses": {},
                "message_types": []
            },
        )
        assert response.status_code == 401

    async def test_fetch_messages_requires_auth(self, client: AsyncClient):
        """Test that fetch_messages requires authentication."""
        response = await client.post(
            "/api/triage/wizard/fetch-messages",
            json={"slack_links": ["https://test.slack.com/archives/C123/p123"]},
        )
        assert response.status_code == 401
