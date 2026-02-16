import logging
from typing import Any

from app.tools.base import BaseTool

logger = logging.getLogger(__name__)

SYNTHESIS_PROMPT = """You are a research analyst. Your job is to evaluate search results for quality and relevance, then synthesize the best ones into a clear answer.

Query: {query}

Search results:
{results_text}

**Evaluation criteria — assess each result before using it:**
- **Relevance**: Does this result directly address the query? Skip tangential results. Use the relevance score as a signal (higher is better), but apply your own judgment too.
- **Recency**: For time-sensitive queries (prices, news, releases, "current" anything), strongly prefer results with recent published dates. Older results may be outdated.
- **Source quality**: Favor authoritative and original sources (official docs, primary reporting, expert analysis) over aggregators, forums, or content farms.
- **Clarity**: Prefer results with concrete facts, numbers, and specifics over vague or generic content.

**Synthesis instructions:**
- You may SKIP low-quality, irrelevant, or redundant results entirely — do not force everything into the summary.
- When multiple sources agree on a fact, state it with confidence.
- When sources conflict, present both sides with their sources and note the disagreement.
- Include specific data points — don't just say "several" or "various", list them.
- Cite sources as [Title](URL).
- If the results don't adequately answer the query, say so explicitly and note what's missing.
- Write at least 200 words. More detail is better than less.
- Do NOT add opinions or information not found in the search results."""


class WebSearchTool(BaseTool):
    """Web search tool using Tavily API with LLM synthesis."""

    name = "web_search"
    description = (
        "Search the web for current information. Use when the user asks about "
        "recent events, current data, news, prices, release dates, or anything "
        "that may have changed after your knowledge cutoff. Tips: be specific "
        "with queries, include dates or year when relevant, use multiple "
        "searches for complex or multi-faceted topics, and refine your query "
        "if initial results are incomplete or low quality."
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
            search_depth=settings.web_search_depth,
            include_answer=False,
        )

        return response.get("results", [])

    def _format_results(self, results: list[dict[str, Any]]) -> str:
        """Format raw search results into text for synthesis, including quality signals."""
        formatted = []
        for i, result in enumerate(results, 1):
            title = result.get("title", "No title")
            url = result.get("url", "")
            content = result.get("content", "No content")

            meta_parts = [f"URL: {url}"]
            if result.get("score") is not None:
                meta_parts.append(f"Relevance Score: {result['score']:.2f}")
            if result.get("published_date"):
                meta_parts.append(f"Published: {result['published_date']}")

            meta_line = " | ".join(meta_parts)
            formatted.append(f"[{i}] {title}\n{meta_line}\n{content}")
        return "\n---\n".join(formatted)

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
