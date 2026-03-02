"""Unit tests for the todo tool and recurrence service."""

import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from app.tools.base import ToolContext
from app.tools.todos import ManageTodosTool
from app.services.recurrence import RecurrenceService


# ---------------------------------------------------------------------------
# ManageTodosTool — Definition tests
# ---------------------------------------------------------------------------


class TestManageTodosToolDefinition:
    """Tests for ManageTodosTool schema and definition."""

    def test_to_definition(self):
        """Should produce a valid ToolDefinition."""
        tool = ManageTodosTool()
        defn = tool.to_definition()

        assert defn.name == "manage_todos"
        assert "todo" in defn.description.lower()
        assert defn.parameters["type"] == "object"
        assert "action" in defn.parameters["properties"]
        assert "action" in defn.parameters["required"]

    def test_user_id_not_in_schema(self):
        """user_id must never appear in the tool's parameter schema."""
        tool = ManageTodosTool()
        props = tool.parameters_schema["properties"]
        assert "user_id" not in props
        assert "user_id" not in tool.parameters_schema.get("required", [])

    def test_action_enum_values(self):
        """Action should have exactly the expected enum values."""
        tool = ManageTodosTool()
        action_prop = tool.parameters_schema["properties"]["action"]
        assert set(action_prop["enum"]) == {
            "create", "list", "update", "complete", "delete",
        }

    def test_only_action_required(self):
        """Only action should be required."""
        tool = ManageTodosTool()
        assert tool.parameters_schema["required"] == ["action"]


# ---------------------------------------------------------------------------
# ManageTodosTool — Execute tests
# ---------------------------------------------------------------------------


class TestManageTodosToolExecute:
    """Tests for ManageTodosTool.execute() with mocked repository."""

    @pytest.fixture
    def tool(self):
        return ManageTodosTool()

    @pytest.fixture
    def context(self):
        return ToolContext(db=AsyncMock(), user_id="user-123")

    async def test_requires_context(self, tool):
        """Should return error when no context provided."""
        result = await tool.execute(action="list")
        assert "error" in result.lower()

    async def test_requires_user_id(self, tool):
        """Should return error when context has no user_id."""
        ctx = ToolContext(db=AsyncMock())
        result = await tool.execute(context=ctx, action="list")
        assert "error" in result.lower()

    async def test_create_todo(self, tool, context):
        """Should create a todo and return confirmation."""
        mock_todo = MagicMock()
        mock_todo.id = "todo-1"
        mock_todo.title = "Buy groceries"
        mock_todo.priority = 1
        mock_todo.due_at = None
        mock_todo.recurrence_rule = None
        mock_todo.tags = []

        with patch("app.db.repositories.todo.TodoRepository") as MockRepo:
            mock_repo = AsyncMock()
            mock_repo.create_todo.return_value = mock_todo
            MockRepo.return_value = mock_repo

            result = await tool.execute(
                context=context, action="create", title="Buy groceries", priority=1,
            )

            mock_repo.create_todo.assert_called_once()
            assert "Buy groceries" in result
            assert "High" in result

    async def test_create_requires_title(self, tool, context):
        """Should return error when title is missing for create."""
        result = await tool.execute(context=context, action="create")
        assert "title" in result.lower() and "required" in result.lower()

    async def test_list_todos(self, tool, context):
        """Should list todos."""
        mock_todo = MagicMock()
        mock_todo.id = "todo-1"
        mock_todo.title = "Test todo"
        mock_todo.priority = 2
        mock_todo.is_starred = False
        mock_todo.due_at = None

        with patch("app.db.repositories.todo.TodoRepository") as MockRepo:
            mock_repo = AsyncMock()
            mock_repo.get_user_todos.return_value = [mock_todo]
            MockRepo.return_value = mock_repo

            result = await tool.execute(context=context, action="list")

            assert "Test todo" in result
            assert "1" in result  # should have numbering

    async def test_list_empty(self, tool, context):
        """Should report no todos when list is empty."""
        with patch("app.db.repositories.todo.TodoRepository") as MockRepo:
            mock_repo = AsyncMock()
            mock_repo.get_user_todos.return_value = []
            MockRepo.return_value = mock_repo

            result = await tool.execute(context=context, action="list")

            assert "no" in result.lower()

    async def test_complete_todo(self, tool, context):
        """Should complete a todo."""
        mock_todo = MagicMock()
        mock_todo.id = "todo-1"
        mock_todo.title = "Done task"
        mock_todo.user_id = "user-123"
        mock_todo.recurrence_rule = None

        with patch("app.db.repositories.todo.TodoRepository") as MockRepo:
            mock_repo = AsyncMock()
            mock_repo.get.return_value = mock_todo
            mock_repo.complete_todo.return_value = mock_todo
            MockRepo.return_value = mock_repo

            with patch("app.worker.scheduler.cancel_todo_reminder", new_callable=AsyncMock):
                result = await tool.execute(
                    context=context, action="complete", todo_id="todo-1",
                )

            assert "completed" in result.lower()
            assert "Done task" in result

    async def test_complete_requires_todo_id(self, tool, context):
        """Should return error when todo_id is missing for complete."""
        result = await tool.execute(context=context, action="complete")
        assert "todo_id" in result.lower() and "required" in result.lower()

    async def test_delete_todo(self, tool, context):
        """Should delete a todo."""
        mock_todo = MagicMock()
        mock_todo.id = "todo-1"
        mock_todo.title = "Delete me"
        mock_todo.user_id = "user-123"

        with patch("app.db.repositories.todo.TodoRepository") as MockRepo:
            mock_repo = AsyncMock()
            mock_repo.get.return_value = mock_todo
            MockRepo.return_value = mock_repo

            with patch("app.worker.scheduler.cancel_todo_reminder", new_callable=AsyncMock):
                result = await tool.execute(
                    context=context, action="delete", todo_id="todo-1",
                )

            assert "deleted" in result.lower()
            assert "Delete me" in result

    async def test_delete_not_found(self, tool, context):
        """Should return error when todo not found."""
        with patch("app.db.repositories.todo.TodoRepository") as MockRepo:
            mock_repo = AsyncMock()
            mock_repo.get.return_value = None
            MockRepo.return_value = mock_repo

            result = await tool.execute(
                context=context, action="delete", todo_id="nonexistent",
            )

            assert "not found" in result.lower()

    async def test_delete_wrong_user(self, tool, context):
        """Should return error when todo belongs to another user."""
        mock_todo = MagicMock()
        mock_todo.id = "todo-1"
        mock_todo.user_id = "other-user"

        with patch("app.db.repositories.todo.TodoRepository") as MockRepo:
            mock_repo = AsyncMock()
            mock_repo.get.return_value = mock_todo
            MockRepo.return_value = mock_repo

            result = await tool.execute(
                context=context, action="delete", todo_id="todo-1",
            )

            assert "not authorized" in result.lower()

    async def test_unknown_action(self, tool, context):
        """Should return error for unknown action."""
        result = await tool.execute(context=context, action="unknown")
        assert "unknown" in result.lower()


# ---------------------------------------------------------------------------
# RecurrenceService tests
# ---------------------------------------------------------------------------


class TestRecurrenceServiceValidate:
    """Tests for RecurrenceService.validate_rrule."""

    def test_valid_daily(self):
        assert RecurrenceService.validate_rrule("FREQ=DAILY;INTERVAL=1") is True

    def test_valid_weekly_byday(self):
        assert RecurrenceService.validate_rrule("FREQ=WEEKLY;BYDAY=MO,WE,FR") is True

    def test_valid_monthly_byday(self):
        assert RecurrenceService.validate_rrule("FREQ=MONTHLY;BYDAY=1MO") is True

    def test_valid_with_rrule_prefix(self):
        assert RecurrenceService.validate_rrule("RRULE:FREQ=WEEKLY;INTERVAL=2;BYDAY=TU") is True

    def test_invalid_empty(self):
        assert RecurrenceService.validate_rrule("") is False

    def test_invalid_garbage(self):
        assert RecurrenceService.validate_rrule("not a valid rule") is False


class TestRecurrenceServiceComputeNext:
    """Tests for RecurrenceService.compute_next_occurrence."""

    def test_daily_next(self):
        after = datetime(2026, 3, 1, 9, 0, tzinfo=timezone.utc)
        result = RecurrenceService.compute_next_occurrence(
            "FREQ=DAILY;INTERVAL=1", after
        )
        assert result is not None
        assert result.day == 2
        assert result.month == 3
        assert result.hour == 9

    def test_weekly_next(self):
        # March 1, 2026 is a Sunday
        after = datetime(2026, 3, 1, 10, 0, tzinfo=timezone.utc)
        result = RecurrenceService.compute_next_occurrence(
            "FREQ=WEEKLY;BYDAY=MO", after
        )
        assert result is not None
        assert result.weekday() == 0  # Monday

    def test_biweekly(self):
        after = datetime(2026, 3, 1, 10, 0, tzinfo=timezone.utc)
        result = RecurrenceService.compute_next_occurrence(
            "FREQ=WEEKLY;INTERVAL=2;BYDAY=SU", after
        )
        assert result is not None
        # Should be 2 weeks from the next Sunday
        assert result > after

    def test_invalid_rule_returns_none(self):
        after = datetime(2026, 3, 1, 10, 0, tzinfo=timezone.utc)
        result = RecurrenceService.compute_next_occurrence("invalid", after)
        assert result is None


class TestRecurrenceServiceHumanReadable:
    """Tests for RecurrenceService.human_readable."""

    def test_daily(self):
        result = RecurrenceService.human_readable("FREQ=DAILY;INTERVAL=1")
        assert "every day" in result.lower()

    def test_weekly_multiple_days(self):
        result = RecurrenceService.human_readable("FREQ=WEEKLY;BYDAY=MO,WE,FR")
        assert "monday" in result.lower()
        assert "wednesday" in result.lower()
        assert "friday" in result.lower()

    def test_biweekly(self):
        result = RecurrenceService.human_readable("FREQ=WEEKLY;INTERVAL=2;BYDAY=TU")
        assert "other" in result.lower() or "2" in result

    def test_monthly_first_monday(self):
        result = RecurrenceService.human_readable("FREQ=MONTHLY;BYDAY=1MO")
        assert "first" in result.lower()
        assert "monday" in result.lower()

    def test_with_rrule_prefix(self):
        result = RecurrenceService.human_readable("RRULE:FREQ=DAILY;INTERVAL=1")
        assert "every day" in result.lower()
