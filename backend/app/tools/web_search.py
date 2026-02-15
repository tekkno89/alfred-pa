import logging
from typing import Any

from app.tools.base import BaseTool

logger = logging.getLogger(__name__)

SYNTHESIS_PROMPT = """You are a research assistant. Your job is to extract and present the key information from web search results.

Query: {query}

Search results:
{results_text}

Instructions:
- Extract ALL relevant facts, dates, numbers, names, and details from the results.
- Include specific data points — don't just say "several" or "various", list them.
- Cite sources as [Title](URL).
- If results contain conflicting information, include both with their sources.
- Write at least 200 words. More detail is better than less.
- Do NOT add opinions or information not found in the search results."""


class WebSearchTool(BaseTool):
    """Web search tool using Tavily API with LLM synthesis."""

    name = "web_search"
    description = (
        "Search the web for current information. Use when the user asks about "
        "recent events, current data, news, prices, release dates, or anything "
        "that may have changed after your knowledge cutoff. Use today's date "
        "(from the system prompt) when forming search queries. "
        "One search per topic is usually sufficient."
    )
    parameters_schema: dict[str, Any] = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "The search query",
            }
        },
        "required": ["query"],
    }

    async def execute(self, **kwargs: Any) -> str:
        """Execute a web search and return a synthesized summary."""
        query = kwargs.get("query", "")
        if not query:
            return "Error: No search query provided."

        try:
            # 1. Call Tavily API
            logger.info(f"Searching Tavily for: {query}")
            raw_results = await self._search_tavily(query)
            if not raw_results:
                logger.warning(f"No search results for: {query}")
                return f"No search results found for: {query}"

            logger.info(f"Tavily returned {len(raw_results)} results")

            # Store metadata for streaming to frontend
            self.last_execution_metadata = {
                "query": query,
                "sources": [
                    {"title": r.get("title", ""), "url": r.get("url", "")}
                    for r in raw_results
                ],
            }

            # 2. Format results for synthesis
            results_text = self._format_results(raw_results)

            # 3. Synthesize with a cheap/fast LLM
            logger.info("Synthesizing search results...")
            summary = await self._synthesize(query, results_text)
            logger.info(f"Synthesis complete, {len(summary)} chars")
            return summary

        except Exception as e:
            logger.error(f"Web search failed for query '{query}': {e}", exc_info=True)
            return f"Web search failed: {str(e)}"

    async def _search_tavily(self, query: str) -> list[dict[str, Any]]:
        """Search using Tavily API."""
        from tavily import AsyncTavilyClient

        from app.core.config import get_settings

        settings = get_settings()
        client = AsyncTavilyClient(api_key=settings.tavily_api_key)

        response = await client.search(
            query=query,
            max_results=settings.web_search_max_results,
            include_answer=False,
        )

        return response.get("results", [])

    def _format_results(self, results: list[dict[str, Any]]) -> str:
        """Format raw search results into text for synthesis."""
        formatted = []
        for i, result in enumerate(results, 1):
            title = result.get("title", "No title")
            url = result.get("url", "")
            content = result.get("content", "No content")
            formatted.append(f"[{i}] {title}\nURL: {url}\n{content}\n")
        return "\n".join(formatted)

    async def _synthesize(self, query: str, results_text: str) -> str:
        """Use a cheap LLM to synthesize search results into a summary."""
        from app.core.config import get_settings
        from app.core.llm import LLMMessage, get_llm_provider

        settings = get_settings()
        provider = get_llm_provider(settings.web_search_synthesis_model)

        prompt = SYNTHESIS_PROMPT.format(query=query, results_text=results_text)
        messages = [LLMMessage(role="user", content=prompt)]

        try:
            summary = await provider.generate(
                messages, temperature=0.3, max_tokens=1024
            )
            return summary
        except Exception as e:
            logger.error(f"Synthesis failed, returning raw results: {e}")
            # Fallback: return formatted results directly
            return f"Search results for '{query}':\n\n{results_text}"
