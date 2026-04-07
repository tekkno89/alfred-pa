from app.core.llm import ToolDefinition
from app.tools.base import BaseTool

_registry_instance: "ToolRegistry | None" = None


class ToolRegistry:
    """Registry of available tools."""

    def __init__(self) -> None:
        self._tools: dict[str, BaseTool] = {}

    def register(self, tool: BaseTool) -> None:
        """Register a tool."""
        self._tools[tool.name] = tool

    def get(self, name: str) -> BaseTool | None:
        """Get a tool by name."""
        return self._tools.get(name)

    def get_definitions(self) -> list[ToolDefinition]:
        """Get ToolDefinitions for all registered tools."""
        return [tool.to_definition() for tool in self._tools.values()]

    def has_tools(self) -> bool:
        """Return True if any tools are registered."""
        return len(self._tools) > 0


def get_tool_registry() -> ToolRegistry:
    """Get or create the singleton tool registry."""
    global _registry_instance
    if _registry_instance is None:
        _registry_instance = ToolRegistry()
        _register_default_tools(_registry_instance)
    return _registry_instance


def _register_default_tools(registry: ToolRegistry) -> None:
    """Register default tools if their dependencies are configured."""
    from app.core.config import get_settings

    settings = get_settings()

    if settings.tavily_api_key:
        from app.tools.web_search import WebSearchTool

        registry.register(WebSearchTool())

    # Focus mode tool — no external API key dependency
    from app.tools.focus_mode import FocusModeTool

    registry.register(FocusModeTool())

    # Todo management tool — no external API key dependency
    from app.tools.todos import ManageTodosTool

    registry.register(ManageTodosTool())

    # Calendar management tool — uses Google Calendar OAuth (no API key)
    from app.tools.calendar import CalendarTool

    registry.register(CalendarTool())

    # YouTube management tool — no external API key dependency
    from app.tools.youtube import ManageYouTubeTool

    registry.register(ManageYouTubeTool())

    # Slack messages tool — search, read conversations, list channels
    from app.tools.slack_messages import SlackMessagesTool

    registry.register(SlackMessagesTool())

    # Coding assistant tool — requires sandbox orchestrator
    if settings.sandbox_url and settings.sandbox_api_key:
        from app.tools.coding_assistant import CodingAssistantTool

        registry.register(CodingAssistantTool())
