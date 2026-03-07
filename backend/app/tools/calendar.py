"""Calendar management tool for the LLM agent."""

import logging
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from app.tools.base import BaseTool, ToolContext

logger = logging.getLogger(__name__)


def _format_event_time(start: str, end: str | None, all_day: bool, user_timezone: str | None) -> str:
    """Format event time for display."""
    if all_day:
        return "All day"

    try:
        start_dt = datetime.fromisoformat(start)
        if user_timezone:
            tz = ZoneInfo(user_timezone)
            start_dt = start_dt.astimezone(tz)

        time_str = start_dt.strftime("%I:%M %p").lstrip("0")

        if end:
            end_dt = datetime.fromisoformat(end)
            if user_timezone:
                end_dt = end_dt.astimezone(ZoneInfo(user_timezone))
            time_str += f" - {end_dt.strftime('%I:%M %p').lstrip('0')}"

        return time_str
    except (ValueError, KeyError):
        return start


class CalendarTool(BaseTool):
    """Tool for managing the user's Google Calendar via the LLM agent."""

    name = "manage_calendar"
    description = (
        "Manage the user's Google Calendar. Actions: "
        '"list_events" shows upcoming events (defaults to today), '
        '"create_event" creates a new event (requires title + start), '
        '"update_event" modifies an existing event (requires event_id), '
        '"delete_event" removes an event (requires event_id). '
        "For dates/times, use ISO 8601 format with timezone offset "
        "(e.g. 2026-03-15T09:00:00-07:00). "
        "For all-day events, use date format (e.g. 2026-03-15)."
    )
    parameters_schema: dict[str, Any] = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["list_events", "create_event", "update_event", "delete_event"],
                "description": "The calendar action to perform.",
            },
            "title": {
                "type": "string",
                "description": "Event title (required for create_event).",
            },
            "description": {
                "type": "string",
                "description": "Event description.",
            },
            "location": {
                "type": "string",
                "description": "Event location.",
            },
            "start": {
                "type": "string",
                "description": "Start date/time in ISO 8601 format.",
            },
            "end": {
                "type": "string",
                "description": "End date/time in ISO 8601 format. Defaults to 1 hour after start.",
            },
            "all_day": {
                "type": "boolean",
                "description": "Whether this is an all-day event.",
            },
            "calendar_id": {
                "type": "string",
                "description": "Calendar ID. Defaults to 'primary'.",
            },
            "account_label": {
                "type": "string",
                "description": "Account label for multi-account. Defaults to 'default'.",
            },
            "event_id": {
                "type": "string",
                "description": "Event ID (required for update_event and delete_event).",
            },
            "attendees": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Email addresses of attendees.",
            },
            "recurrence": {
                "type": "array",
                "items": {"type": "string"},
                "description": "RRULE strings for recurring events.",
            },
            "time_min": {
                "type": "string",
                "description": "Start of date range for list_events (ISO 8601). Defaults to today.",
            },
            "time_max": {
                "type": "string",
                "description": "End of date range for list_events (ISO 8601). Defaults to end of today.",
            },
            "scope": {
                "type": "string",
                "enum": ["this", "all"],
                "description": "For recurring events: 'this' for single instance, 'all' for all instances.",
            },
        },
        "required": ["action"],
    }

    async def execute(self, *, context: ToolContext | None = None, **kwargs: Any) -> str:
        """Execute a calendar management action."""
        if not context or "user_id" not in context or "db" not in context:
            return "Error: Calendar management requires an authenticated session."

        user_id = context["user_id"]
        db = context["db"]
        user_timezone = context.get("timezone")
        action = kwargs.get("action", "")

        try:
            if action == "list_events":
                return await self._handle_list_events(db, user_id, kwargs, user_timezone)
            elif action == "create_event":
                return await self._handle_create_event(db, user_id, kwargs, user_timezone)
            elif action == "update_event":
                return await self._handle_update_event(db, user_id, kwargs, user_timezone)
            elif action == "delete_event":
                return await self._handle_delete_event(db, user_id, kwargs)
            else:
                return f"Error: Unknown action '{action}'. Use list_events, create_event, update_event, or delete_event."
        except Exception as e:
            logger.error(f"Calendar tool error (action={action}): {e}", exc_info=True)
            return f"Error performing calendar action: {str(e)}"

    async def _handle_list_events(
        self, db, user_id: str, kwargs: dict, user_timezone: str | None
    ) -> str:
        from app.db.repositories.dashboard import DashboardPreferenceRepository
        from app.services.google_calendar import (
            CALENDAR_COLOR_PALETTE,
            GoogleCalendarService,
        )

        # Determine time range (default: today in user's timezone)
        if user_timezone:
            try:
                tz = ZoneInfo(user_timezone)
            except (KeyError, ValueError):
                tz = ZoneInfo("UTC")
        else:
            tz = ZoneInfo("UTC")

        now = datetime.now(tz)

        time_min = kwargs.get("time_min")
        time_max = kwargs.get("time_max")

        if not time_min:
            start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0)
            time_min = start_of_day.isoformat()
        if not time_max:
            if not kwargs.get("time_min"):
                end_of_day = now.replace(hour=23, minute=59, second=59, microsecond=0)
                time_max = end_of_day.isoformat()
            else:
                # If time_min specified but not time_max, default to 7 days
                start_dt = datetime.fromisoformat(time_min)
                time_max = (start_dt + timedelta(days=7)).isoformat()

        # Get visible calendar configs
        pref_repo = DashboardPreferenceRepository(db)
        pref = await pref_repo.get_by_user_and_card(user_id, "calendar")
        prefs = (pref.preferences or {}).get("calendars", []) if pref else []

        if prefs:
            configs = [p for p in prefs if p.get("visible", True)]
        else:
            service = GoogleCalendarService(db)
            calendars = await service.list_all_calendars_for_user(user_id)
            configs = [
                {
                    "account_label": cal.get("account_label", "default"),
                    "calendar_id": cal["id"],
                    "color": CALENDAR_COLOR_PALETTE[i % len(CALENDAR_COLOR_PALETTE)],
                }
                for i, cal in enumerate(calendars)
            ]

        if not configs:
            return "No calendars connected. Connect a Google Calendar account in Settings > Integrations."

        service = GoogleCalendarService(db)
        events = await service.list_events_for_user(user_id, configs, time_min, time_max)

        if not events:
            return "No events found for the specified time range."

        lines = [f"Events ({len(events)}):"]
        for event in events:
            time_str = _format_event_time(
                event["start"], event.get("end"), event.get("all_day", False), user_timezone
            )
            title = event.get("title", "(No title)")
            location = event.get("location")
            event_id = event["id"]

            line = f"- {time_str}: {title}"
            if location:
                line += f" ({location})"
            line += f" [ID: {event_id}]"
            lines.append(line)

        return "\n".join(lines)

    async def _handle_create_event(
        self, db, user_id: str, kwargs: dict, user_timezone: str | None
    ) -> str:
        from app.services.google_calendar import GoogleCalendarService

        title = kwargs.get("title")
        if not title:
            return "Error: 'title' is required for creating an event."

        start = kwargs.get("start")
        if not start:
            return "Error: 'start' is required for creating an event."

        calendar_id = kwargs.get("calendar_id", "primary")
        account_label = kwargs.get("account_label", "default")
        all_day = kwargs.get("all_day", False)

        body: dict = {"summary": title}

        if kwargs.get("description"):
            body["description"] = kwargs["description"]
        if kwargs.get("location"):
            body["location"] = kwargs["location"]

        if all_day:
            body["start"] = {"date": start}
            body["end"] = {"date": kwargs.get("end", start)}
        else:
            body["start"] = {"dateTime": start}
            end = kwargs.get("end")
            if end:
                body["end"] = {"dateTime": end}
            else:
                try:
                    start_dt = datetime.fromisoformat(start)
                    end_dt = start_dt + timedelta(hours=1)
                    body["end"] = {"dateTime": end_dt.isoformat()}
                except ValueError:
                    body["end"] = {"dateTime": start}

        if kwargs.get("attendees"):
            body["attendees"] = [{"email": email} for email in kwargs["attendees"]]

        if kwargs.get("recurrence"):
            body["recurrence"] = kwargs["recurrence"]

        service = GoogleCalendarService(db)
        event = await service.create_event(user_id, account_label, calendar_id, body)

        time_str = _format_event_time(
            event["start"], event.get("end"), event.get("all_day", False), user_timezone
        )
        result = f'Event created: "{event["title"]}" at {time_str}'
        if event.get("location"):
            result += f"\nLocation: {event['location']}"
        result += f"\nID: {event['id']}"

        self.last_execution_metadata = {
            "event_id": event["id"],
            "title": event["title"],
            "action": "created",
        }

        return result

    async def _handle_update_event(
        self, db, user_id: str, kwargs: dict, user_timezone: str | None
    ) -> str:
        from app.services.google_calendar import GoogleCalendarService

        event_id = kwargs.get("event_id")
        if not event_id:
            return "Error: 'event_id' is required for updating an event."

        calendar_id = kwargs.get("calendar_id", "primary")
        account_label = kwargs.get("account_label", "default")

        body: dict = {}
        if kwargs.get("title") is not None:
            body["summary"] = kwargs["title"]
        if kwargs.get("description") is not None:
            body["description"] = kwargs["description"]
        if kwargs.get("location") is not None:
            body["location"] = kwargs["location"]

        all_day = kwargs.get("all_day", False)
        if kwargs.get("start") is not None:
            if all_day:
                body["start"] = {"date": kwargs["start"]}
            else:
                body["start"] = {"dateTime": kwargs["start"]}
        if kwargs.get("end") is not None:
            if all_day:
                body["end"] = {"date": kwargs["end"]}
            else:
                body["end"] = {"dateTime": kwargs["end"]}

        if kwargs.get("attendees") is not None:
            body["attendees"] = [{"email": email} for email in kwargs["attendees"]]

        if kwargs.get("recurrence") is not None:
            body["recurrence"] = kwargs["recurrence"]

        if not body:
            return "No updates provided."

        service = GoogleCalendarService(db)
        event = await service.update_event(user_id, account_label, calendar_id, event_id, body)

        time_str = _format_event_time(
            event["start"], event.get("end"), event.get("all_day", False), user_timezone
        )
        result = f'Event updated: "{event["title"]}" at {time_str}'
        result += f"\nID: {event['id']}"

        self.last_execution_metadata = {
            "event_id": event["id"],
            "title": event["title"],
            "action": "updated",
        }

        return result

    async def _handle_delete_event(self, db, user_id: str, kwargs: dict) -> str:
        from app.services.google_calendar import GoogleCalendarService

        event_id = kwargs.get("event_id")
        if not event_id:
            return "Error: 'event_id' is required for deleting an event."

        calendar_id = kwargs.get("calendar_id", "primary")
        account_label = kwargs.get("account_label", "default")

        service = GoogleCalendarService(db)
        await service.delete_event(user_id, account_label, calendar_id, event_id)

        self.last_execution_metadata = {
            "event_id": event_id,
            "action": "deleted",
        }

        return f"Event deleted (ID: {event_id})"
