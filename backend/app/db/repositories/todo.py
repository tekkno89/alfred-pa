"""Todo repository."""

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.todo import Todo
from app.db.repositories.base import BaseRepository


class TodoRepository(BaseRepository[Todo]):
    """Repository for Todo model."""

    def __init__(self, db: AsyncSession):
        super().__init__(Todo, db)

    async def create_todo(
        self,
        user_id: str,
        title: str,
        description: str | None = None,
        priority: int = 2,
        due_at: datetime | None = None,
        is_starred: bool = False,
        tags: list[str] | None = None,
        recurrence_rule: str | None = None,
        recurrence_parent_id: str | None = None,
    ) -> Todo:
        """Create a new todo."""
        todo = Todo(
            user_id=user_id,
            title=title,
            description=description,
            priority=priority,
            due_at=due_at,
            is_starred=is_starred,
            tags=tags or [],
            recurrence_rule=recurrence_rule,
            recurrence_parent_id=recurrence_parent_id,
        )
        return await self.create(todo)

    async def get_user_todos(
        self,
        user_id: str,
        *,
        status: str | None = None,
        priority: int | None = None,
        starred: bool | None = None,
        due_before: datetime | None = None,
        due_after: datetime | None = None,
        tags: list[str] | None = None,
        skip: int = 0,
        limit: int = 20,
        sort_by: str = "created_at",
        sort_order: str = "desc",
    ) -> list[Todo]:
        """Get todos for a user with filters and sorting."""
        query = select(Todo).where(Todo.user_id == user_id)

        if status is not None:
            query = query.where(Todo.status == status)
        if priority is not None:
            query = query.where(Todo.priority == priority)
        if starred is not None:
            query = query.where(Todo.is_starred == starred)
        if due_before is not None:
            query = query.where(Todo.due_at <= due_before)
        if due_after is not None:
            query = query.where(Todo.due_at >= due_after)
        if tags:
            query = query.where(Todo.tags.overlap(tags))

        order_col = getattr(Todo, sort_by, Todo.created_at)
        if sort_order == "asc":
            query = query.order_by(order_col.asc())
        else:
            query = query.order_by(order_col.desc())

        query = query.offset(skip).limit(limit)
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def count_user_todos(
        self,
        user_id: str,
        *,
        status: str | None = None,
        priority: int | None = None,
        starred: bool | None = None,
        due_before: datetime | None = None,
        due_after: datetime | None = None,
        tags: list[str] | None = None,
    ) -> int:
        """Count todos for a user with filters."""
        query = (
            select(func.count())
            .select_from(Todo)
            .where(Todo.user_id == user_id)
        )

        if status is not None:
            query = query.where(Todo.status == status)
        if priority is not None:
            query = query.where(Todo.priority == priority)
        if starred is not None:
            query = query.where(Todo.is_starred == starred)
        if due_before is not None:
            query = query.where(Todo.due_at <= due_before)
        if due_after is not None:
            query = query.where(Todo.due_at >= due_after)
        if tags:
            query = query.where(Todo.tags.overlap(tags))

        result = await self.db.execute(query)
        return result.scalar() or 0

    async def get_summary_counts(
        self, user_id: str, tz_name: str | None = None
    ) -> dict[str, int]:
        """Get summary counts for dashboard card."""
        now = datetime.now(UTC)

        # Resolve user timezone (fall back to UTC for invalid/missing)
        try:
            user_tz = ZoneInfo(tz_name) if tz_name else UTC
        except (KeyError, ValueError):
            user_tz = UTC

        local_now = now.astimezone(user_tz)
        today_end = local_now.replace(
            hour=23, minute=59, second=59, microsecond=999999
        ).astimezone(UTC)
        # End of week (next Sunday 23:59:59 in user's timezone)
        days_until_sunday = 6 - local_now.weekday()
        if days_until_sunday < 0:
            days_until_sunday = 0
        week_end = (
            local_now.replace(hour=23, minute=59, second=59, microsecond=999999)
            + timedelta(days=days_until_sunday)
        ).astimezone(UTC)

        # Overdue: due_at < now
        overdue_q = (
            select(func.count())
            .select_from(Todo)
            .where(Todo.user_id == user_id, Todo.status == "open", Todo.due_at < now)
        )
        overdue_result = await self.db.execute(overdue_q)
        overdue = overdue_result.scalar() or 0

        # Due today: due_at between now and end of today
        today_q = (
            select(func.count())
            .select_from(Todo)
            .where(
                Todo.user_id == user_id,
                Todo.status == "open",
                Todo.due_at >= now,
                Todo.due_at <= today_end,
            )
        )
        today_result = await self.db.execute(today_q)
        due_today = today_result.scalar() or 0

        # Due this week: due_at between now and end of week
        week_q = (
            select(func.count())
            .select_from(Todo)
            .where(
                Todo.user_id == user_id,
                Todo.status == "open",
                Todo.due_at >= now,
                Todo.due_at <= week_end,
            )
        )
        week_result = await self.db.execute(week_q)
        due_this_week = week_result.scalar() or 0

        # Total open
        total_q = (
            select(func.count())
            .select_from(Todo)
            .where(Todo.user_id == user_id, Todo.status == "open")
        )
        total_result = await self.db.execute(total_q)
        total_open = total_result.scalar() or 0

        return {
            "overdue": overdue,
            "due_today": due_today,
            "due_this_week": due_this_week,
            "total_open": total_open,
        }

    async def get_dashboard_items(self, user_id: str, limit: int = 5) -> list[Todo]:
        """Get starred + highest priority open items for dashboard."""
        query = (
            select(Todo)
            .where(Todo.user_id == user_id, Todo.status == "open")
            .order_by(
                case((Todo.is_starred == True, 0), else_=1),  # noqa: E712
                Todo.priority.asc(),
                Todo.due_at.asc().nulls_last(),
            )
            .limit(limit)
        )
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def get_due_reminders(self, now: datetime) -> list[Todo]:
        """Get todos past due that haven't had a reminder sent."""
        query = (
            select(Todo)
            .where(
                Todo.status == "open",
                Todo.due_at <= now,
                Todo.due_at.isnot(None),
                Todo.reminder_sent_at.is_(None),
            )
        )
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def complete_todo(self, todo: Todo) -> Todo:
        """Mark a todo as completed."""
        return await self.update(
            todo,
            status="completed",
            completed_at=datetime.now(UTC),
        )

    async def update_todo(self, todo: Todo, **updates: object) -> Todo:
        """Update a todo's fields."""
        return await self.update(todo, **updates)
