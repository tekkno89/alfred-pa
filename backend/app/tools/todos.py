"""Todo management tool for the LLM agent."""

import logging
from datetime import UTC, datetime
from typing import Any

from app.tools.base import BaseTool, ToolContext

logger = logging.getLogger(__name__)

PRIORITY_LABELS = {0: "Urgent", 1: "High", 2: "Medium", 3: "Low"}


class ManageTodosTool(BaseTool):
    """Tool for managing the user's todo list via the LLM agent."""

    name = "manage_todos"
    description = (
        "Manage the user's todo list. Actions: "
        '"create" adds a new todo, '
        '"list" shows todos (optionally filtered), '
        '"update" modifies an existing todo, '
        '"complete" marks a todo as done, '
        '"delete" removes a todo. '
        "For due dates, use ISO 8601 format (e.g. 2026-03-15T09:00:00Z). "
        "For recurrence, convert to RFC 5545 RRULE "
        '(e.g. "FREQ=DAILY;INTERVAL=1", "FREQ=WEEKLY;BYDAY=MO,WE,FR").'
    )
    parameters_schema: dict[str, Any] = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["create", "list", "update", "complete", "delete"],
                "description": "The todo action to perform.",
            },
            "title": {
                "type": "string",
                "description": "Title for the todo (required for create).",
            },
            "description": {
                "type": "string",
                "description": "Optional description for the todo.",
            },
            "priority": {
                "type": "integer",
                "minimum": 0,
                "maximum": 3,
                "description": "Priority: 0=Urgent, 1=High, 2=Medium, 3=Low.",
            },
            "due_at": {
                "type": "string",
                "description": "Due date/time in ISO 8601 format.",
            },
            "is_starred": {
                "type": "boolean",
                "description": "Whether the todo is starred/pinned.",
            },
            "tags": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Tags for categorization.",
            },
            "recurrence_rule": {
                "type": "string",
                "description": "RFC 5545 RRULE for recurring todos.",
            },
            "todo_id": {
                "type": "string",
                "description": "Todo ID (required for update/complete/delete).",
            },
            "status": {
                "type": "string",
                "enum": ["open", "completed"],
                "description": "Filter by status (for list action).",
            },
            "filter_priority": {
                "type": "integer",
                "minimum": 0,
                "maximum": 3,
                "description": "Filter by priority (for list action).",
            },
        },
        "required": ["action"],
    }

    async def execute(self, *, context: ToolContext | None = None, **kwargs: Any) -> str:
        """Execute a todo management action."""
        if not context or "user_id" not in context or "db" not in context:
            return "Error: Todo management requires an authenticated session."

        user_id = context["user_id"]
        db = context["db"]
        action = kwargs.get("action", "")

        try:
            if action == "create":
                return await self._handle_create(db, user_id, kwargs)
            elif action == "list":
                return await self._handle_list(db, user_id, kwargs)
            elif action == "update":
                return await self._handle_update(db, user_id, kwargs)
            elif action == "complete":
                return await self._handle_complete(db, user_id, kwargs)
            elif action == "delete":
                return await self._handle_delete(db, user_id, kwargs)
            else:
                return f"Error: Unknown action '{action}'. Use create, list, update, complete, or delete."
        except Exception as e:
            logger.error(f"Todo tool error (action={action}): {e}", exc_info=True)
            return f"Error performing todo action: {str(e)}"

    async def _handle_create(self, db, user_id: str, kwargs: dict) -> str:
        from app.db.repositories.todo import TodoRepository

        title = kwargs.get("title")
        if not title:
            return "Error: 'title' is required for creating a todo."

        due_at = None
        if kwargs.get("due_at"):
            try:
                due_at = datetime.fromisoformat(kwargs["due_at"].replace("Z", "+00:00"))
            except ValueError:
                return f"Error: Invalid due_at format: {kwargs['due_at']}. Use ISO 8601."

        recurrence_rule = kwargs.get("recurrence_rule")
        if recurrence_rule:
            from app.services.recurrence import RecurrenceService

            if not RecurrenceService.validate_rrule(recurrence_rule):
                return f"Error: Invalid recurrence rule: {recurrence_rule}"

        repo = TodoRepository(db)
        todo = await repo.create_todo(
            user_id=user_id,
            title=title,
            description=kwargs.get("description"),
            priority=kwargs.get("priority", 2),
            due_at=due_at,
            is_starred=kwargs.get("is_starred", False),
            tags=kwargs.get("tags", []),
            recurrence_rule=recurrence_rule,
        )

        # Schedule reminder if due_at is set
        if todo.due_at:
            try:
                from app.worker.scheduler import schedule_todo_reminder

                job_id = await schedule_todo_reminder(todo.id, user_id, todo.due_at)
                if job_id:
                    await repo.update_todo(todo, reminder_job_id=job_id)
            except Exception:
                pass

        priority_label = PRIORITY_LABELS.get(todo.priority, "Medium")
        parts = [f'Todo created: "{todo.title}" (Priority: {priority_label})']
        if todo.due_at:
            parts.append(f"Due: {todo.due_at.strftime('%B %d, %Y at %I:%M %p %Z')}")
        if todo.recurrence_rule:
            from app.services.recurrence import RecurrenceService

            parts.append(f"Recurrence: {RecurrenceService.human_readable(todo.recurrence_rule)}")
        if todo.tags:
            parts.append(f"Tags: {', '.join(todo.tags)}")
        parts.append(f"ID: {todo.id}")
        return "\n".join(parts)

    async def _handle_list(self, db, user_id: str, kwargs: dict) -> str:
        from app.db.repositories.todo import TodoRepository

        repo = TodoRepository(db)
        status_filter = kwargs.get("status", "open")
        priority_filter = kwargs.get("filter_priority")

        todos = await repo.get_user_todos(
            user_id=user_id,
            status=status_filter,
            priority=priority_filter,
            limit=20,
            sort_by="priority",
            sort_order="asc",
        )

        if not todos:
            return f"No {status_filter} todos found."

        lines = [f"Your {status_filter} todos ({len(todos)}):"]
        for i, todo in enumerate(todos, 1):
            priority_label = PRIORITY_LABELS.get(todo.priority, "Medium")
            star = " *" if todo.is_starred else ""
            due = ""
            if todo.due_at:
                now = datetime.now(UTC)
                if todo.due_at < now:
                    due = " [OVERDUE]"
                else:
                    due = f" (due {todo.due_at.strftime('%b %d, %I:%M %p')})"
            lines.append(
                f"{i}. [{priority_label}]{star} {todo.title}{due} — ID: {todo.id}"
            )

        return "\n".join(lines)

    async def _handle_update(self, db, user_id: str, kwargs: dict) -> str:
        from app.db.repositories.todo import TodoRepository

        todo_id = kwargs.get("todo_id")
        if not todo_id:
            return "Error: 'todo_id' is required for updating a todo."

        repo = TodoRepository(db)
        todo = await repo.get(todo_id)

        if not todo:
            return f"Error: Todo not found with ID: {todo_id}"
        if todo.user_id != user_id:
            return "Error: Not authorized to update this todo."

        updates: dict[str, Any] = {}
        if kwargs.get("title") is not None:
            updates["title"] = kwargs["title"]
        if kwargs.get("description") is not None:
            updates["description"] = kwargs["description"]
        if kwargs.get("priority") is not None:
            updates["priority"] = kwargs["priority"]
        if kwargs.get("is_starred") is not None:
            updates["is_starred"] = kwargs["is_starred"]
        if kwargs.get("tags") is not None:
            updates["tags"] = kwargs["tags"]
        if kwargs.get("recurrence_rule") is not None:
            from app.services.recurrence import RecurrenceService

            if kwargs["recurrence_rule"] and not RecurrenceService.validate_rrule(kwargs["recurrence_rule"]):
                return f"Error: Invalid recurrence rule: {kwargs['recurrence_rule']}"
            updates["recurrence_rule"] = kwargs["recurrence_rule"]

        old_due_at = todo.due_at
        if kwargs.get("due_at") is not None:
            try:
                updates["due_at"] = datetime.fromisoformat(
                    kwargs["due_at"].replace("Z", "+00:00")
                )
            except ValueError:
                return f"Error: Invalid due_at format: {kwargs['due_at']}"

        if not updates:
            return "No updates provided."

        todo = await repo.update_todo(todo, **updates)

        # Reschedule reminder if due_at changed
        if "due_at" in updates and todo.due_at != old_due_at:
            try:
                from app.worker.scheduler import (
                    cancel_todo_reminder,
                    schedule_todo_reminder,
                )

                await cancel_todo_reminder(todo.id)
                if todo.due_at:
                    job_id = await schedule_todo_reminder(todo.id, user_id, todo.due_at)
                    if job_id:
                        await repo.update_todo(todo, reminder_job_id=job_id, reminder_sent_at=None)
            except Exception:
                pass

        return f'Todo updated: "{todo.title}" (ID: {todo.id})'

    async def _handle_complete(self, db, user_id: str, kwargs: dict) -> str:
        from app.db.repositories.todo import TodoRepository

        todo_id = kwargs.get("todo_id")
        if not todo_id:
            return "Error: 'todo_id' is required for completing a todo."

        repo = TodoRepository(db)
        todo = await repo.get(todo_id)

        if not todo:
            return f"Error: Todo not found with ID: {todo_id}"
        if todo.user_id != user_id:
            return "Error: Not authorized to complete this todo."

        todo = await repo.complete_todo(todo)

        # Cancel any pending reminder
        try:
            from app.worker.scheduler import cancel_todo_reminder

            await cancel_todo_reminder(todo.id)
        except Exception:
            pass

        result = f'Todo completed: "{todo.title}"'

        # Handle recurrence
        if todo.recurrence_rule:
            from app.services.recurrence import RecurrenceService

            new_todo = await RecurrenceService.create_next_occurrence(db, todo)
            if new_todo:
                due_str = ""
                if new_todo.due_at:
                    due_str = f" (due {new_todo.due_at.strftime('%b %d, %I:%M %p')})"
                result += f"\nNext occurrence created{due_str} — ID: {new_todo.id}"

        return result

    async def _handle_delete(self, db, user_id: str, kwargs: dict) -> str:
        from app.db.repositories.todo import TodoRepository

        todo_id = kwargs.get("todo_id")
        if not todo_id:
            return "Error: 'todo_id' is required for deleting a todo."

        repo = TodoRepository(db)
        todo = await repo.get(todo_id)

        if not todo:
            return f"Error: Todo not found with ID: {todo_id}"
        if todo.user_id != user_id:
            return "Error: Not authorized to delete this todo."

        title = todo.title

        # Cancel any pending reminder
        try:
            from app.worker.scheduler import cancel_todo_reminder

            await cancel_todo_reminder(todo.id)
        except Exception:
            pass

        await repo.delete(todo)
        return f'Todo deleted: "{title}"'
