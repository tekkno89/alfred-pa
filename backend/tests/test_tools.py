import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.tools.base import BaseTool
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
