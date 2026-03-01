"""Focus mode tool for the LLM agent."""

import logging
from typing import Any

from app.tools.base import BaseTool, ToolContext

logger = logging.getLogger(__name__)


class FocusModeTool(BaseTool):
    """Tool for managing focus mode sessions via the LLM agent."""

    name = "focus_mode"
    description = (
        "Manage focus mode for the current user. Actions: "
        '"enable" starts focus mode (optionally with a duration in minutes and custom message), '
        '"disable" turns it off, '
        '"status" checks current focus state, '
        '"start_pomodoro" begins a pomodoro session (optionally with work/break durations and session count), '
        '"skip_phase" skips to the next pomodoro phase or ends the session.'
    )
    parameters_schema: dict[str, Any] = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["enable", "disable", "status", "start_pomodoro", "skip_phase"],
                "description": "The focus mode action to perform.",
            },
            "duration_minutes": {
                "type": "integer",
                "minimum": 1,
                "maximum": 480,
                "description": "Duration in minutes for the enable action. If omitted, focus mode stays on until manually disabled.",
            },
            "custom_message": {
                "type": "string",
                "description": "Custom auto-reply message for enable or start_pomodoro.",
            },
            "work_minutes": {
                "type": "integer",
                "minimum": 1,
                "maximum": 120,
                "description": "Work phase duration for start_pomodoro (default: user setting or 25).",
            },
            "break_minutes": {
                "type": "integer",
                "minimum": 1,
                "maximum": 60,
                "description": "Break phase duration for start_pomodoro (default: user setting or 5).",
            },
            "total_sessions": {
                "type": "integer",
                "minimum": 1,
                "maximum": 12,
                "description": "Number of pomodoro sessions for start_pomodoro.",
            },
        },
        "required": ["action"],
    }

    async def execute(self, *, context: ToolContext | None = None, **kwargs: Any) -> str:
        """Execute a focus mode action. user_id comes from context, never kwargs."""
        if not context or "user_id" not in context or "db" not in context:
            return "Error: Focus mode requires an authenticated session."

        user_id = context["user_id"]
        db = context["db"]
        action = kwargs.get("action", "")

        # Lazy import to avoid circular imports at module level
        from app.services.focus_orchestrator import FocusModeOrchestrator

        orchestrator = FocusModeOrchestrator(db)

        try:
            if action == "enable":
                return await self._handle_enable(orchestrator, user_id, kwargs)
            elif action == "disable":
                return await self._handle_disable(orchestrator, user_id)
            elif action == "status":
                return await self._handle_status(orchestrator, user_id)
            elif action == "start_pomodoro":
                return await self._handle_start_pomodoro(orchestrator, user_id, kwargs)
            elif action == "skip_phase":
                return await self._handle_skip_phase(orchestrator, user_id)
            else:
                return f"Error: Unknown action '{action}'. Use enable, disable, status, start_pomodoro, or skip_phase."
        except Exception as e:
            logger.error(f"Focus mode tool error (action={action}): {e}", exc_info=True)
            return f"Error performing focus mode action: {str(e)}"

    # ------------------------------------------------------------------
    # Action handlers
    # ------------------------------------------------------------------

    async def _handle_enable(
        self, orchestrator: Any, user_id: str, kwargs: dict
    ) -> str:
        result = await orchestrator.enable(
            user_id=user_id,
            duration_minutes=kwargs.get("duration_minutes"),
            custom_message=kwargs.get("custom_message"),
        )
        if result.ends_at:
            remaining = result.time_remaining_seconds or 0
            mins = remaining // 60
            return f"Focus mode enabled for {mins} minutes. Slack status updated and notifications silenced."
        return "Focus mode enabled (no time limit). Slack status updated and notifications silenced."

    async def _handle_disable(self, orchestrator: Any, user_id: str) -> str:
        await orchestrator.disable(user_id=user_id)
        return "Focus mode disabled. Slack status restored and notifications resumed."

    async def _handle_status(self, orchestrator: Any, user_id: str) -> str:
        result = await orchestrator.get_status(user_id=user_id)
        if not result.is_active:
            return "Focus mode is currently off."

        parts = [f"Focus mode is active (mode: {result.mode})."]
        if result.time_remaining_seconds is not None:
            mins = result.time_remaining_seconds // 60
            parts.append(f"Time remaining: {mins} minutes.")
        if result.mode == "pomodoro":
            parts.append(f"Phase: {result.pomodoro_phase}.")
            parts.append(
                f"Session {result.pomodoro_session_count}"
                + (f" of {result.pomodoro_total_sessions}" if result.pomodoro_total_sessions else "")
                + "."
            )
        if result.custom_message:
            parts.append(f'Auto-reply message: "{result.custom_message}"')
        return " ".join(parts)

    async def _handle_start_pomodoro(
        self, orchestrator: Any, user_id: str, kwargs: dict
    ) -> str:
        result = await orchestrator.start_pomodoro(
            user_id=user_id,
            custom_message=kwargs.get("custom_message"),
            work_minutes=kwargs.get("work_minutes"),
            break_minutes=kwargs.get("break_minutes"),
            total_sessions=kwargs.get("total_sessions"),
        )
        work = result.pomodoro_work_minutes or 25
        brk = result.pomodoro_break_minutes or 5
        sessions_info = f" for {result.pomodoro_total_sessions} sessions" if result.pomodoro_total_sessions else ""
        return (
            f"Pomodoro started{sessions_info}: {work}-minute work / {brk}-minute break. "
            f"Currently in work phase (session {result.pomodoro_session_count}). "
            "Slack status updated and notifications silenced."
        )

    async def _handle_skip_phase(self, orchestrator: Any, user_id: str) -> str:
        result = await orchestrator.skip_pomodoro_phase(user_id=user_id)
        if not result.is_active:
            return "Pomodoro complete! All sessions finished. Focus mode disabled, Slack status restored."
        return (
            f"Skipped to {result.pomodoro_phase} phase "
            f"(session {result.pomodoro_session_count}"
            + (f" of {result.pomodoro_total_sessions}" if result.pomodoro_total_sessions else "")
            + "). Slack status updated."
        )
