"""Integration tests for the todos API endpoints."""

import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, patch
from zoneinfo import ZoneInfo

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.todo import Todo
from app.db.models.dashboard import UserFeatureAccess
from tests.conftest import auth_headers
from tests.factories import UserFactory


@pytest.fixture
async def test_user(db_session: AsyncSession):
    """Create a test user with todos feature access."""
    user = UserFactory()
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    # Grant todos feature access
    access = UserFeatureAccess(
        user_id=user.id,
        feature_key="card:todos",
        enabled=True,
        granted_by=user.id,
    )
    db_session.add(access)
    await db_session.commit()

    return user


@pytest.fixture
async def other_user(db_session: AsyncSession):
    """Create another user."""
    user = UserFactory()
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest.fixture
async def sample_todo(db_session: AsyncSession, test_user):
    """Create a sample todo."""
    todo = Todo(
        user_id=test_user.id,
        title="Test todo",
        description="A test description",
        priority=2,
        status="open",
        is_starred=False,
        tags=["test"],
    )
    db_session.add(todo)
    await db_session.commit()
    await db_session.refresh(todo)
    return todo


class TestCreateTodo:
    """Tests for POST /api/todos."""

    async def test_create_basic(self, client: AsyncClient, test_user):
        """Should create a todo with required fields."""
        response = await client.post(
            "/api/todos",
            json={"title": "Buy milk"},
            headers=auth_headers(test_user),
        )

        assert response.status_code == 201
        data = response.json()
        assert data["title"] == "Buy milk"
        assert data["status"] == "open"
        assert data["priority"] == 2
        assert data["is_starred"] is False

    async def test_create_with_all_fields(self, client: AsyncClient, test_user):
        """Should create a todo with all optional fields."""
        due = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
        response = await client.post(
            "/api/todos",
            json={
                "title": "Important task",
                "description": "Details here",
                "priority": 0,
                "due_at": due,
                "is_starred": True,
                "tags": ["work", "urgent"],
            },
            headers=auth_headers(test_user),
        )

        assert response.status_code == 201
        data = response.json()
        assert data["title"] == "Important task"
        assert data["priority"] == 0
        assert data["is_starred"] is True
        assert data["tags"] == ["work", "urgent"]
        assert data["due_at"] is not None

    async def test_create_invalid_recurrence(self, client: AsyncClient, test_user):
        """Should reject invalid recurrence rule."""
        response = await client.post(
            "/api/todos",
            json={"title": "Bad recurrence", "recurrence_rule": "INVALID"},
            headers=auth_headers(test_user),
        )

        assert response.status_code == 400

    async def test_create_no_access(self, client: AsyncClient, other_user):
        """Should deny access without feature flag."""
        response = await client.post(
            "/api/todos",
            json={"title": "No access"},
            headers=auth_headers(other_user),
        )

        assert response.status_code == 403


class TestListTodos:
    """Tests for GET /api/todos."""

    async def test_list_empty(self, client: AsyncClient, test_user):
        """Should return empty list."""
        response = await client.get(
            "/api/todos",
            headers=auth_headers(test_user),
        )

        assert response.status_code == 200
        data = response.json()
        assert data["items"] == []
        assert data["total"] == 0

    async def test_list_with_data(
        self, client: AsyncClient, test_user, sample_todo,
    ):
        """Should return user's todos."""
        response = await client.get(
            "/api/todos",
            headers=auth_headers(test_user),
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 1
        assert data["items"][0]["title"] == "Test todo"

    async def test_list_filter_by_status(
        self, client: AsyncClient, db_session, test_user, sample_todo,
    ):
        """Should filter by status."""
        response = await client.get(
            "/api/todos?status=completed",
            headers=auth_headers(test_user),
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 0

    async def test_list_filter_by_priority(
        self, client: AsyncClient, test_user, sample_todo,
    ):
        """Should filter by priority."""
        response = await client.get(
            "/api/todos?priority=0",
            headers=auth_headers(test_user),
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 0  # sample_todo is priority 2

    async def test_list_filter_by_starred(
        self, client: AsyncClient, test_user, sample_todo,
    ):
        """Should filter by starred."""
        response = await client.get(
            "/api/todos?starred=true",
            headers=auth_headers(test_user),
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 0  # sample_todo is not starred


class TestGetTodo:
    """Tests for GET /api/todos/{id}."""

    async def test_get_existing(
        self, client: AsyncClient, test_user, sample_todo,
    ):
        """Should return a specific todo."""
        response = await client.get(
            f"/api/todos/{sample_todo.id}",
            headers=auth_headers(test_user),
        )

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == sample_todo.id
        assert data["title"] == "Test todo"

    async def test_get_not_found(self, client: AsyncClient, test_user):
        """Should return 404 for non-existent todo."""
        response = await client.get(
            "/api/todos/nonexistent-id",
            headers=auth_headers(test_user),
        )

        assert response.status_code == 404

    async def test_get_other_users_todo(
        self, client: AsyncClient, other_user, sample_todo, db_session,
    ):
        """Should deny access to another user's todo."""
        # Grant other user access
        access = UserFeatureAccess(
            user_id=other_user.id,
            feature_key="card:todos",
            enabled=True,
            granted_by=other_user.id,
        )
        db_session.add(access)
        await db_session.commit()

        response = await client.get(
            f"/api/todos/{sample_todo.id}",
            headers=auth_headers(other_user),
        )

        assert response.status_code == 403


class TestUpdateTodo:
    """Tests for PUT /api/todos/{id}."""

    async def test_update_title(
        self, client: AsyncClient, test_user, sample_todo,
    ):
        """Should update a todo's title."""
        response = await client.put(
            f"/api/todos/{sample_todo.id}",
            json={"title": "Updated title"},
            headers=auth_headers(test_user),
        )

        assert response.status_code == 200
        data = response.json()
        assert data["title"] == "Updated title"

    async def test_update_priority(
        self, client: AsyncClient, test_user, sample_todo,
    ):
        """Should update priority."""
        response = await client.put(
            f"/api/todos/{sample_todo.id}",
            json={"priority": 0},
            headers=auth_headers(test_user),
        )

        assert response.status_code == 200
        assert response.json()["priority"] == 0


class TestCompleteTodo:
    """Tests for PATCH /api/todos/{id}/complete."""

    async def test_complete(
        self, client: AsyncClient, test_user, sample_todo,
    ):
        """Should mark todo as completed."""
        response = await client.patch(
            f"/api/todos/{sample_todo.id}/complete",
            headers=auth_headers(test_user),
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "completed"
        assert data["completed_at"] is not None

    async def test_complete_recurring_creates_next(
        self, client: AsyncClient, db_session, test_user,
    ):
        """Completing a recurring todo should create the next occurrence."""
        due = datetime.now(timezone.utc) + timedelta(hours=1)
        todo = Todo(
            user_id=test_user.id,
            title="Daily standup",
            priority=2,
            status="open",
            due_at=due,
            recurrence_rule="FREQ=DAILY;INTERVAL=1",
            tags=[],
        )
        db_session.add(todo)
        await db_session.commit()
        await db_session.refresh(todo)

        response = await client.patch(
            f"/api/todos/{todo.id}/complete",
            headers=auth_headers(test_user),
        )

        assert response.status_code == 200
        assert response.json()["status"] == "completed"

        # Check that a new occurrence was created
        list_response = await client.get(
            "/api/todos?status=open",
            headers=auth_headers(test_user),
        )
        open_todos = list_response.json()["items"]
        assert len(open_todos) >= 1
        next_todo = [t for t in open_todos if t["title"] == "Daily standup"]
        assert len(next_todo) == 1
        assert next_todo[0]["recurrence_rule"] == "FREQ=DAILY;INTERVAL=1"
        assert next_todo[0]["recurrence_parent_id"] == todo.id


class TestDeleteTodo:
    """Tests for DELETE /api/todos/{id}."""

    async def test_delete(
        self, client: AsyncClient, test_user, sample_todo,
    ):
        """Should delete a todo."""
        response = await client.delete(
            f"/api/todos/{sample_todo.id}",
            headers=auth_headers(test_user),
        )

        assert response.status_code == 200
        assert response.json()["success"] is True

        # Verify it's gone
        get_response = await client.get(
            f"/api/todos/{sample_todo.id}",
            headers=auth_headers(test_user),
        )
        assert get_response.status_code == 404


class TestTodoSummary:
    """Tests for GET /api/todos/summary."""

    async def test_summary_empty(self, client: AsyncClient, test_user):
        """Should return zero counts when no todos."""
        response = await client.get(
            "/api/todos/summary",
            headers=auth_headers(test_user),
        )

        assert response.status_code == 200
        data = response.json()
        assert data["overdue"] == 0
        assert data["due_today"] == 0
        assert data["due_this_week"] == 0
        assert data["total_open"] == 0

    async def test_summary_counts(
        self, client: AsyncClient, db_session, test_user,
    ):
        """Should return correct summary counts."""
        now = datetime.now(timezone.utc)

        # Overdue todo
        overdue = Todo(
            user_id=test_user.id, title="Overdue",
            priority=0, status="open", tags=[],
            due_at=now - timedelta(hours=2),
        )
        # Due today todo
        today_todo = Todo(
            user_id=test_user.id, title="Today",
            priority=1, status="open", tags=[],
            due_at=now + timedelta(hours=2),
        )
        # No due date (still open)
        no_due = Todo(
            user_id=test_user.id, title="No due date",
            priority=2, status="open", tags=[],
        )
        db_session.add_all([overdue, today_todo, no_due])
        await db_session.commit()

        response = await client.get(
            "/api/todos/summary",
            headers=auth_headers(test_user),
        )

        assert response.status_code == 200
        data = response.json()
        assert data["overdue"] == 1
        assert data["total_open"] == 3


class TestTodoDashboard:
    """Tests for GET /api/todos/dashboard."""

    async def test_dashboard_items(
        self, client: AsyncClient, db_session, test_user,
    ):
        """Should return starred and high-priority items first."""
        starred = Todo(
            user_id=test_user.id, title="Starred",
            priority=3, status="open", is_starred=True, tags=[],
        )
        urgent = Todo(
            user_id=test_user.id, title="Urgent",
            priority=0, status="open", is_starred=False, tags=[],
        )
        low = Todo(
            user_id=test_user.id, title="Low priority",
            priority=3, status="open", is_starred=False, tags=[],
        )
        db_session.add_all([starred, urgent, low])
        await db_session.commit()

        response = await client.get(
            "/api/todos/dashboard",
            headers=auth_headers(test_user),
        )

        assert response.status_code == 200
        items = response.json()
        assert len(items) == 3
        # Starred should be first, then urgent
        assert items[0]["title"] == "Starred"
        assert items[1]["title"] == "Urgent"


class TestTodoSummaryTimezone:
    """Tests for timezone-aware summary counts."""

    async def test_summary_respects_timezone_boundary(
        self, client: AsyncClient, db_session, test_user,
    ):
        """A todo due tonight UTC but tomorrow in UTC+14 should not count as 'today' for UTC+14."""
        now = datetime.now(timezone.utc)
        # Set due_at to 23:30 UTC today — still "today" in UTC,
        # but already tomorrow in Pacific/Kiritimati (UTC+14)
        due = now.replace(hour=23, minute=30, second=0, microsecond=0)
        # If it's already past 23:30 UTC, push to tomorrow
        if due <= now:
            due += timedelta(days=1)

        todo = Todo(
            user_id=test_user.id, title="Late UTC",
            priority=1, status="open", tags=[],
            due_at=due,
        )
        db_session.add(todo)
        await db_session.commit()

        # With UTC — should be due today
        resp_utc = await client.get(
            "/api/todos/summary?tz=UTC",
            headers=auth_headers(test_user),
        )
        assert resp_utc.status_code == 200
        data_utc = resp_utc.json()
        assert data_utc["due_today"] == 1

        # With Pacific/Kiritimati (UTC+14) — 23:30 UTC is 13:30 next day
        resp_kiri = await client.get(
            "/api/todos/summary?tz=Pacific/Kiritimati",
            headers=auth_headers(test_user),
        )
        assert resp_kiri.status_code == 200
        data_kiri = resp_kiri.json()
        # It's tomorrow in Kiritimati, so not due "today"
        assert data_kiri["due_today"] == 0

    async def test_summary_invalid_timezone_falls_back(
        self, client: AsyncClient, test_user,
    ):
        """Invalid timezone should fall back to UTC without error."""
        response = await client.get(
            "/api/todos/summary?tz=Not/A/Timezone",
            headers=auth_headers(test_user),
        )

        assert response.status_code == 200
        data = response.json()
        # Should still return valid counts (all zeros for no todos)
        assert data["overdue"] == 0
        assert data["due_today"] == 0
        assert data["due_this_week"] == 0
        assert data["total_open"] == 0

    async def test_summary_backward_compat_no_tz(
        self, client: AsyncClient, test_user,
    ):
        """Omitting tz param should still work (backward compatible)."""
        response = await client.get(
            "/api/todos/summary",
            headers=auth_headers(test_user),
        )

        assert response.status_code == 200
        data = response.json()
        assert "overdue" in data
        assert "due_today" in data
        assert "due_this_week" in data
        assert "total_open" in data
