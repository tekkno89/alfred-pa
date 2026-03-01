import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.tools.base import BaseTool, ToolContext
from app.tools.focus_mode import FocusModeTool
from app.tools.registry import ToolRegistry
from app.tools.web_search import WebSearchTool


class TestWebSearchToolDefinition:
    """Tests for WebSearchTool schema and definition."""

    def test_to_definition(self):
        """Should produce a valid ToolDefinition."""
        tool = WebSearchTool()
        defn = tool.to_definition()

        assert defn.name == "web_search"
        assert "search" in defn.description.lower()
        assert defn.parameters["type"] == "object"
        assert "query" in defn.parameters["properties"]
        assert "query" in defn.parameters["required"]

    def test_name_and_description(self):
        """Tool should have name and description set."""
        tool = WebSearchTool()
        assert tool.name == "web_search"
        assert len(tool.description) > 0


class TestWebSearchToolExecute:
    """Tests for WebSearchTool.execute() with mocks."""

    async def test_execute_success(self):
        """Should search, synthesize, and return a summary."""
        tool = WebSearchTool()

        mock_results = [
            {
                "title": "Test Article",
                "url": "https://example.com/article",
                "content": "This is test content about Python 3.13.",
            },
            {
                "title": "Another Article",
                "url": "https://example.com/another",
                "content": "More information about Python features.",
            },
        ]

        with patch.object(tool, "_search_tavily", new_callable=AsyncMock) as mock_search, \
             patch.object(tool, "_synthesize", new_callable=AsyncMock) as mock_synth:
            mock_search.return_value = mock_results
            mock_synth.return_value = "Python 3.13 brings pattern matching improvements. [Source](https://example.com/article)"

            result = await tool.execute(query="Python 3.13 features")

            mock_search.assert_called_once_with("Python 3.13 features")
            mock_synth.assert_called_once()
            assert "Python 3.13" in result

    async def test_execute_sets_metadata(self):
        """Should populate last_execution_metadata with query and sources after successful execute."""
        tool = WebSearchTool()

        mock_results = [
            {
                "title": "Test Article",
                "url": "https://example.com/article",
                "content": "Test content.",
            },
            {
                "title": "Another Article",
                "url": "https://example.com/another",
                "content": "More content.",
            },
        ]

        with patch.object(tool, "_search_tavily", new_callable=AsyncMock) as mock_search, \
             patch.object(tool, "_synthesize", new_callable=AsyncMock) as mock_synth:
            mock_search.return_value = mock_results
            mock_synth.return_value = "Summary text"

            assert tool.last_execution_metadata is None
            await tool.execute(query="test query")

            assert tool.last_execution_metadata is not None
            assert tool.last_execution_metadata["query"] == "test query"
            assert len(tool.last_execution_metadata["sources"]) == 2
            assert tool.last_execution_metadata["sources"][0] == {
                "title": "Test Article",
                "url": "https://example.com/article",
            }
            assert tool.last_execution_metadata["sources"][1] == {
                "title": "Another Article",
                "url": "https://example.com/another",
            }

    async def test_execute_empty_query(self):
        """Should return error for empty query."""
        tool = WebSearchTool()
        result = await tool.execute(query="")
        assert "error" in result.lower() or "no search query" in result.lower()

    async def test_execute_no_results(self):
        """Should handle no results gracefully."""
        tool = WebSearchTool()

        with patch.object(tool, "_search_tavily", new_callable=AsyncMock) as mock_search:
            mock_search.return_value = []

            result = await tool.execute(query="xyznonexistent")
            assert "no search results" in result.lower()

    async def test_execute_tavily_error(self):
        """Should handle Tavily API failure gracefully."""
        tool = WebSearchTool()

        with patch.object(tool, "_search_tavily", new_callable=AsyncMock) as mock_search:
            mock_search.side_effect = Exception("API rate limit exceeded")

            result = await tool.execute(query="test query")
            assert "failed" in result.lower() or "error" in result.lower()

    async def test_execute_synthesis_fallback(self):
        """Should fall back to raw results if synthesis fails."""
        tool = WebSearchTool()

        mock_results = [
            {
                "title": "Test",
                "url": "https://example.com",
                "content": "Test content",
            },
        ]

        with patch.object(tool, "_search_tavily", new_callable=AsyncMock) as mock_search, \
             patch.object(tool, "_synthesize", new_callable=AsyncMock) as mock_synth:
            mock_search.return_value = mock_results
            # Synthesis fails but _synthesize itself handles the fallback
            mock_synth.return_value = "Search results for 'test':\n\n[1] Test\nURL: https://example.com\nTest content\n"

            result = await tool.execute(query="test")
            assert "Test" in result


class TestToolRegistry:
    """Tests for ToolRegistry."""

    def test_register_and_get(self):
        """Should register and retrieve tools."""
        registry = ToolRegistry()
        tool = WebSearchTool()
        registry.register(tool)

        assert registry.get("web_search") is tool
        assert registry.get("nonexistent") is None

    def test_get_definitions(self):
        """Should return definitions for all registered tools."""
        registry = ToolRegistry()
        registry.register(WebSearchTool())

        defs = registry.get_definitions()
        assert len(defs) == 1
        assert defs[0].name == "web_search"

    def test_has_tools(self):
        """Should report whether tools are registered."""
        registry = ToolRegistry()
        assert registry.has_tools() is False

        registry.register(WebSearchTool())
        assert registry.has_tools() is True

    def test_empty_definitions(self):
        """Should return empty list when no tools registered."""
        registry = ToolRegistry()
        assert registry.get_definitions() == []


class TestFormatResults:
    """Tests for WebSearchTool._format_results."""

    def test_format_results_with_metadata(self):
        """Should format results with relevance score and published date."""
        tool = WebSearchTool()
        results = [
            {
                "title": "Title 1",
                "url": "https://example.com/1",
                "content": "Content 1",
                "score": 0.95,
                "published_date": "2025-12-01",
            },
            {
                "title": "Title 2",
                "url": "https://example.com/2",
                "content": "Content 2",
                "score": 0.72,
                "published_date": "2025-11-15",
            },
        ]

        formatted = tool._format_results(results)
        assert "[1] Title 1" in formatted
        assert "[2] Title 2" in formatted
        assert "https://example.com/1" in formatted
        assert "Content 1" in formatted
        assert "Relevance Score: 0.95" in formatted
        assert "Relevance Score: 0.72" in formatted
        assert "Published: 2025-12-01" in formatted
        assert "Published: 2025-11-15" in formatted
        assert "---" in formatted

    def test_format_results_missing_metadata(self):
        """Should handle results without score or published_date gracefully."""
        tool = WebSearchTool()
        results = [
            {"title": "Title 1", "url": "https://example.com/1", "content": "Content 1"},
            {
                "title": "Title 2",
                "url": "https://example.com/2",
                "content": "Content 2",
                "score": 0.80,
            },
        ]

        formatted = tool._format_results(results)
        assert "[1] Title 1" in formatted
        assert "[2] Title 2" in formatted
        assert "Relevance Score:" not in formatted.split("---")[0]
        assert "Published:" not in formatted
        assert "Relevance Score: 0.80" in formatted


# =========================================================================
# FocusModeTool tests
# =========================================================================


class TestFocusModeToolDefinition:
    """Tests for FocusModeTool schema and definition."""

    def test_to_definition(self):
        """Should produce a valid ToolDefinition."""
        tool = FocusModeTool()
        defn = tool.to_definition()

        assert defn.name == "focus_mode"
        assert "focus" in defn.description.lower()
        assert defn.parameters["type"] == "object"
        assert "action" in defn.parameters["properties"]
        assert "action" in defn.parameters["required"]

    def test_user_id_not_in_schema(self):
        """user_id must never appear in the tool's parameter schema."""
        tool = FocusModeTool()
        props = tool.parameters_schema["properties"]
        assert "user_id" not in props
        # Also check required list
        assert "user_id" not in tool.parameters_schema.get("required", [])

    def test_action_enum_values(self):
        """Action should have exactly the expected enum values."""
        tool = FocusModeTool()
        action_prop = tool.parameters_schema["properties"]["action"]
        assert set(action_prop["enum"]) == {
            "enable",
            "disable",
            "status",
            "start_pomodoro",
            "skip_phase",
        }

    def test_optional_parameters(self):
        """Optional parameters should exist but not be required."""
        tool = FocusModeTool()
        props = tool.parameters_schema["properties"]
        assert "duration_minutes" in props
        assert "custom_message" in props
        assert "work_minutes" in props
        assert "break_minutes" in props
        assert "total_sessions" in props
        # Only action is required
        assert tool.parameters_schema["required"] == ["action"]


class TestFocusModeToolExecute:
    """Tests for FocusModeTool.execute() with mocked orchestrator."""

    @pytest.fixture
    def tool(self):
        return FocusModeTool()

    @pytest.fixture
    def context(self):
        return ToolContext(db=AsyncMock(), user_id="user-123")

    async def test_execute_enable(self, tool, context):
        """Should call orchestrator.enable and return human-readable result."""
        from app.schemas.focus import FocusStatusResponse

        mock_result = FocusStatusResponse(
            is_active=True, mode="simple", ends_at=None
        )

        with patch(
            "app.services.focus_orchestrator.FocusModeOrchestrator"
        ) as MockOrch:
            mock_orch = AsyncMock()
            mock_orch.enable.return_value = mock_result
            MockOrch.return_value = mock_orch

            result = await tool.execute(
                context=context, action="enable", duration_minutes=30
            )

            mock_orch.enable.assert_called_once_with(
                user_id="user-123",
                duration_minutes=30,
                custom_message=None,
            )
            assert "enabled" in result.lower()

    async def test_execute_disable(self, tool, context):
        """Should call orchestrator.disable."""
        from app.schemas.focus import FocusStatusResponse

        with patch(
            "app.services.focus_orchestrator.FocusModeOrchestrator"
        ) as MockOrch:
            mock_orch = AsyncMock()
            mock_orch.disable.return_value = FocusStatusResponse(is_active=False)
            MockOrch.return_value = mock_orch

            result = await tool.execute(context=context, action="disable")

            mock_orch.disable.assert_called_once_with(user_id="user-123")
            assert "disabled" in result.lower()

    async def test_execute_status_active(self, tool, context):
        """Should return active status description."""
        from app.schemas.focus import FocusStatusResponse

        with patch(
            "app.services.focus_orchestrator.FocusModeOrchestrator"
        ) as MockOrch:
            mock_orch = AsyncMock()
            mock_orch.get_status.return_value = FocusStatusResponse(
                is_active=True,
                mode="simple",
                time_remaining_seconds=1800,
            )
            MockOrch.return_value = mock_orch

            result = await tool.execute(context=context, action="status")

            assert "active" in result.lower()
            assert "30 minutes" in result

    async def test_execute_status_inactive(self, tool, context):
        """Should report focus mode as off."""
        from app.schemas.focus import FocusStatusResponse

        with patch(
            "app.services.focus_orchestrator.FocusModeOrchestrator"
        ) as MockOrch:
            mock_orch = AsyncMock()
            mock_orch.get_status.return_value = FocusStatusResponse(is_active=False)
            MockOrch.return_value = mock_orch

            result = await tool.execute(context=context, action="status")

            assert "off" in result.lower()

    async def test_execute_start_pomodoro(self, tool, context):
        """Should call orchestrator.start_pomodoro."""
        from app.schemas.focus import FocusStatusResponse

        with patch(
            "app.services.focus_orchestrator.FocusModeOrchestrator"
        ) as MockOrch:
            mock_orch = AsyncMock()
            mock_orch.start_pomodoro.return_value = FocusStatusResponse(
                is_active=True,
                mode="pomodoro",
                pomodoro_phase="work",
                pomodoro_session_count=1,
                pomodoro_total_sessions=4,
                pomodoro_work_minutes=25,
                pomodoro_break_minutes=5,
            )
            MockOrch.return_value = mock_orch

            result = await tool.execute(
                context=context,
                action="start_pomodoro",
                work_minutes=25,
                total_sessions=4,
            )

            mock_orch.start_pomodoro.assert_called_once_with(
                user_id="user-123",
                custom_message=None,
                work_minutes=25,
                break_minutes=None,
                total_sessions=4,
            )
            assert "pomodoro" in result.lower()

    async def test_execute_skip_phase(self, tool, context):
        """Should call orchestrator.skip_pomodoro_phase."""
        from app.schemas.focus import FocusStatusResponse

        with patch(
            "app.services.focus_orchestrator.FocusModeOrchestrator"
        ) as MockOrch:
            mock_orch = AsyncMock()
            mock_orch.skip_pomodoro_phase.return_value = FocusStatusResponse(
                is_active=True,
                mode="pomodoro",
                pomodoro_phase="break",
                pomodoro_session_count=1,
            )
            MockOrch.return_value = mock_orch

            result = await tool.execute(context=context, action="skip_phase")

            mock_orch.skip_pomodoro_phase.assert_called_once_with(user_id="user-123")
            assert "break" in result.lower()

    async def test_execute_unknown_action(self, tool, context):
        """Should return error for unknown action."""
        result = await tool.execute(context=context, action="invalid")
        assert "error" in result.lower()
        assert "unknown action" in result.lower()

    async def test_execute_missing_context(self, tool):
        """Should return error when context is missing."""
        result = await tool.execute(context=None, action="status")
        assert "error" in result.lower()
        assert "authenticated" in result.lower()

    async def test_execute_missing_user_id_in_context(self, tool):
        """Should return error when user_id is missing from context."""
        ctx = ToolContext(db=AsyncMock())
        result = await tool.execute(context=ctx, action="status")
        assert "error" in result.lower()

    async def test_execute_uses_context_user_id_not_kwargs(self, tool, context):
        """Security test: tool must use context user_id, ignoring any user_id in kwargs."""
        from app.schemas.focus import FocusStatusResponse

        with patch(
            "app.services.focus_orchestrator.FocusModeOrchestrator"
        ) as MockOrch:
            mock_orch = AsyncMock()
            mock_orch.get_status.return_value = FocusStatusResponse(is_active=False)
            MockOrch.return_value = mock_orch

            # Pass a different user_id in kwargs (simulating prompt injection)
            await tool.execute(
                context=context, action="status", user_id="attacker-id"
            )

            # Orchestrator should have been called with the context user_id
            mock_orch.get_status.assert_called_once_with(user_id="user-123")

    async def test_execute_handles_orchestrator_exception(self, tool, context):
        """Should catch exceptions and return error string."""
        with patch(
            "app.services.focus_orchestrator.FocusModeOrchestrator"
        ) as MockOrch:
            mock_orch = AsyncMock()
            mock_orch.enable.side_effect = Exception("Database connection failed")
            MockOrch.return_value = mock_orch

            result = await tool.execute(context=context, action="enable")

            assert "error" in result.lower()
            assert "Database connection failed" in result
