"""Recurrence service for RFC 5545 RRULE parsing and next occurrence computation."""

import logging
from datetime import UTC, datetime

from dateutil.rrule import rrulestr

logger = logging.getLogger(__name__)

# Human-readable frequency names
_FREQ_NAMES = {
    "DAILY": "day",
    "WEEKLY": "week",
    "MONTHLY": "month",
    "YEARLY": "year",
}

_DAY_NAMES = {
    "MO": "Monday",
    "TU": "Tuesday",
    "WE": "Wednesday",
    "TH": "Thursday",
    "FR": "Friday",
    "SA": "Saturday",
    "SU": "Sunday",
}


class RecurrenceService:
    """Service for working with RFC 5545 RRULE recurrence rules."""

    @staticmethod
    def validate_rrule(rrule_string: str) -> bool:
        """Validate an RRULE string. Returns True if valid."""
        try:
            # Ensure it starts with proper prefix for parsing
            rule_str = rrule_string
            if not rule_str.startswith("RRULE:") and not rule_str.startswith("DTSTART"):
                rule_str = f"RRULE:{rule_str}"
            rrulestr(rule_str, dtstart=datetime.now(UTC))
            return True
        except (ValueError, TypeError):
            return False

    @staticmethod
    def compute_next_occurrence(
        rrule_string: str, after: datetime
    ) -> datetime | None:
        """Compute the next occurrence after a given datetime."""
        try:
            rule_str = rrule_string
            if not rule_str.startswith("RRULE:") and not rule_str.startswith("DTSTART"):
                rule_str = f"RRULE:{rule_str}"

            # Use the after time as dtstart for relative calculation
            rule = rrulestr(rule_str, dtstart=after)
            # Get the next occurrence strictly after the given time
            next_dt = rule.after(after, inc=False)
            if next_dt is None:
                return None
            # Preserve timezone
            if after.tzinfo and next_dt.tzinfo is None:
                next_dt = next_dt.replace(tzinfo=after.tzinfo)
            return next_dt
        except (ValueError, TypeError) as e:
            logger.error(f"Failed to compute next occurrence for {rrule_string!r}: {e}")
            return None

    @staticmethod
    def human_readable(rrule_string: str) -> str:
        """Convert an RRULE string to a human-readable description."""
        try:
            # Parse the RRULE components manually for readable output
            parts = rrule_string.replace("RRULE:", "").split(";")
            params: dict[str, str] = {}
            for part in parts:
                if "=" in part:
                    key, value = part.split("=", 1)
                    params[key] = value

            freq = params.get("FREQ", "")
            interval = int(params.get("INTERVAL", "1"))
            byday = params.get("BYDAY", "")

            freq_name = _FREQ_NAMES.get(freq, freq.lower())

            if freq == "WEEKLY" and byday:
                day_parts = byday.split(",")
                day_names = []
                for d in day_parts:
                    # Handle positional days like "1MO" (first Monday)
                    day_abbr = d[-2:]
                    day_names.append(_DAY_NAMES.get(day_abbr, d))

                if interval == 1:
                    return f"Every {', '.join(day_names)}"
                elif interval == 2:
                    return f"Every other {', '.join(day_names)}"
                else:
                    return f"Every {interval} weeks on {', '.join(day_names)}"

            if freq == "MONTHLY" and byday:
                day_parts = byday.split(",")
                descriptions = []
                for d in day_parts:
                    if len(d) > 2:
                        pos = d[:-2]
                        day_abbr = d[-2:]
                        ordinals = {"1": "First", "2": "Second", "3": "Third", "4": "Fourth", "-1": "Last"}
                        ordinal = ordinals.get(pos, f"#{pos}")
                        day_name = _DAY_NAMES.get(day_abbr, d)
                        descriptions.append(f"{ordinal} {day_name}")
                    else:
                        day_name = _DAY_NAMES.get(d, d)
                        descriptions.append(day_name)
                return f"{', '.join(descriptions)} of each month"

            if interval == 1:
                return f"Every {freq_name}"
            elif interval == 2 and freq == "WEEKLY":
                return "Every other week"
            else:
                return f"Every {interval} {freq_name}s"

        except Exception:
            return rrule_string

    @staticmethod
    async def create_next_occurrence(db, completed_todo) -> object | None:
        """
        Create the next occurrence of a recurring todo after completion.

        Args:
            db: Database session
            completed_todo: The todo that was just completed

        Returns:
            The newly created Todo, or None if no more occurrences
        """
        from app.db.repositories.todo import TodoRepository

        if not completed_todo.recurrence_rule:
            return None

        # Compute next due_at
        base_time = completed_todo.due_at or completed_todo.completed_at
        if not base_time:
            base_time = datetime.now(UTC)

        next_due = RecurrenceService.compute_next_occurrence(
            completed_todo.recurrence_rule, base_time
        )
        if not next_due:
            return None

        # Determine the recurrence parent
        parent_id = (
            completed_todo.recurrence_parent_id or completed_todo.id
        )

        repo = TodoRepository(db)
        new_todo = await repo.create_todo(
            user_id=completed_todo.user_id,
            title=completed_todo.title,
            description=completed_todo.description,
            priority=completed_todo.priority,
            due_at=next_due,
            is_starred=completed_todo.is_starred,
            tags=list(completed_todo.tags) if completed_todo.tags else [],
            recurrence_rule=completed_todo.recurrence_rule,
            recurrence_parent_id=parent_id,
        )

        # Schedule reminder for the new todo
        try:
            from app.worker.scheduler import schedule_todo_reminder

            job_id = await schedule_todo_reminder(
                new_todo.id, new_todo.user_id, next_due
            )
            if job_id:
                await repo.update_todo(new_todo, reminder_job_id=job_id)
        except Exception as e:
            logger.warning(f"Failed to schedule reminder for recurring todo: {e}")

        return new_todo
