"""Todos API endpoints."""

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status

from app.api.deps import CurrentUser, DbSession
from app.db.repositories.dashboard import FeatureAccessRepository
from app.db.repositories.todo import TodoRepository
from app.schemas.session import DeleteResponse
from app.schemas.todo import (
    TodoCreate,
    TodoList,
    TodoResponse,
    TodoSummary,
    TodoUpdate,
)

router = APIRouter()


async def _check_todos_access(user: CurrentUser, db: DbSession) -> None:
    """Check that the user has card:todos feature access."""
    if user.role == "admin":
        return
    repo = FeatureAccessRepository(db)
    if not await repo.is_enabled(user.id, "card:todos"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Todos access not enabled",
        )


@router.get("", response_model=TodoList)
async def list_todos(
    db: DbSession,
    user: CurrentUser,
    page: Annotated[int, Query(ge=1)] = 1,
    size: Annotated[int, Query(ge=1, le=100)] = 50,
    sort_by: Annotated[str, Query()] = "created_at",
    sort_order: Annotated[str, Query()] = "desc",
    todo_status: Annotated[str | None, Query(alias="status")] = None,
    priority: Annotated[int | None, Query(ge=0, le=3)] = None,
    starred: Annotated[bool | None, Query()] = None,
    due_before: Annotated[datetime | None, Query()] = None,
    due_after: Annotated[datetime | None, Query()] = None,
) -> TodoList:
    """List todos for the current user with filtering and sorting."""
    await _check_todos_access(user, db)

    repo = TodoRepository(db)
    skip = (page - 1) * size

    todos = await repo.get_user_todos(
        user_id=user.id,
        status=todo_status,
        priority=priority,
        starred=starred,
        due_before=due_before,
        due_after=due_after,
        skip=skip,
        limit=size,
        sort_by=sort_by,
        sort_order=sort_order,
    )
    total = await repo.count_user_todos(
        user_id=user.id,
        status=todo_status,
        priority=priority,
        starred=starred,
        due_before=due_before,
        due_after=due_after,
    )

    return TodoList(
        items=[TodoResponse.model_validate(t) for t in todos],
        total=total,
        page=page,
        size=size,
    )


@router.get("/summary", response_model=TodoSummary)
async def get_todo_summary(
    db: DbSession,
    user: CurrentUser,
    tz: Annotated[str | None, Query(max_length=50)] = None,
) -> TodoSummary:
    """Get summary counts for dashboard card."""
    await _check_todos_access(user, db)

    repo = TodoRepository(db)
    counts = await repo.get_summary_counts(user.id, tz_name=tz)
    return TodoSummary(**counts)


@router.get("/dashboard", response_model=list[TodoResponse])
async def get_dashboard_todos(
    db: DbSession,
    user: CurrentUser,
) -> list[TodoResponse]:
    """Get starred + urgent open todos for dashboard card."""
    await _check_todos_access(user, db)

    repo = TodoRepository(db)
    todos = await repo.get_dashboard_items(user.id, limit=5)
    return [TodoResponse.model_validate(t) for t in todos]


@router.get("/{todo_id}", response_model=TodoResponse)
async def get_todo(
    todo_id: str,
    db: DbSession,
    user: CurrentUser,
) -> TodoResponse:
    """Get a specific todo by ID."""
    await _check_todos_access(user, db)

    repo = TodoRepository(db)
    todo = await repo.get(todo_id)

    if not todo:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Todo not found",
        )

    if todo.user_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to access this todo",
        )

    return TodoResponse.model_validate(todo)


@router.post("", response_model=TodoResponse, status_code=status.HTTP_201_CREATED)
async def create_todo(
    todo_data: TodoCreate,
    db: DbSession,
    user: CurrentUser,
) -> TodoResponse:
    """Create a new todo."""
    await _check_todos_access(user, db)

    # Validate recurrence rule if provided
    if todo_data.recurrence_rule:
        from app.services.recurrence import RecurrenceService

        if not RecurrenceService.validate_rrule(todo_data.recurrence_rule):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid recurrence rule",
            )

    repo = TodoRepository(db)
    todo = await repo.create_todo(
        user_id=user.id,
        title=todo_data.title,
        description=todo_data.description,
        priority=todo_data.priority,
        due_at=todo_data.due_at,
        is_starred=todo_data.is_starred,
        tags=todo_data.tags,
        recurrence_rule=todo_data.recurrence_rule,
    )

    # Schedule reminder if due_at is set
    if todo.due_at:
        try:
            from app.worker.scheduler import schedule_todo_reminder

            job_id = await schedule_todo_reminder(todo.id, user.id, todo.due_at)
            if job_id:
                await repo.update_todo(todo, reminder_job_id=job_id)
        except Exception:
            pass  # Non-critical — reminder scheduling failure shouldn't block creation

    return TodoResponse.model_validate(todo)


@router.put("/{todo_id}", response_model=TodoResponse)
async def update_todo(
    todo_id: str,
    todo_data: TodoUpdate,
    db: DbSession,
    user: CurrentUser,
) -> TodoResponse:
    """Update a todo."""
    await _check_todos_access(user, db)

    repo = TodoRepository(db)
    todo = await repo.get(todo_id)

    if not todo:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Todo not found",
        )

    if todo.user_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to update this todo",
        )

    # Validate recurrence rule if provided
    if todo_data.recurrence_rule is not None and todo_data.recurrence_rule:
        from app.services.recurrence import RecurrenceService

        if not RecurrenceService.validate_rrule(todo_data.recurrence_rule):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid recurrence rule",
            )

    updates = todo_data.model_dump(exclude_none=True)
    old_due_at = todo.due_at

    if updates:
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
                job_id = await schedule_todo_reminder(
                    todo.id, user.id, todo.due_at
                )
                if job_id:
                    await repo.update_todo(
                        todo, reminder_job_id=job_id, reminder_sent_at=None
                    )
            else:
                await repo.update_todo(todo, reminder_job_id=None)
        except Exception:
            pass

    return TodoResponse.model_validate(todo)


@router.patch("/{todo_id}/complete", response_model=TodoResponse)
async def complete_todo(
    todo_id: str,
    db: DbSession,
    user: CurrentUser,
) -> TodoResponse:
    """Mark a todo as completed. Creates next occurrence if recurring."""
    await _check_todos_access(user, db)

    repo = TodoRepository(db)
    todo = await repo.get(todo_id)

    if not todo:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Todo not found",
        )

    if todo.user_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to complete this todo",
        )

    todo = await repo.complete_todo(todo)

    # Cancel any pending reminder
    try:
        from app.worker.scheduler import cancel_todo_reminder

        await cancel_todo_reminder(todo.id)
    except Exception:
        pass

    # Handle recurrence — create next occurrence
    if todo.recurrence_rule:
        try:
            from app.services.recurrence import RecurrenceService

            await RecurrenceService.create_next_occurrence(db, todo)
        except Exception:
            pass

    return TodoResponse.model_validate(todo)


@router.delete("/{todo_id}", response_model=DeleteResponse)
async def delete_todo(
    todo_id: str,
    db: DbSession,
    user: CurrentUser,
) -> DeleteResponse:
    """Permanently delete a todo."""
    await _check_todos_access(user, db)

    repo = TodoRepository(db)
    todo = await repo.get(todo_id)

    if not todo:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Todo not found",
        )

    if todo.user_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to delete this todo",
        )

    # Cancel any pending reminder
    try:
        from app.worker.scheduler import cancel_todo_reminder

        await cancel_todo_reminder(todo.id)
    except Exception:
        pass

    await repo.delete(todo)
    return DeleteResponse(success=True)
