# Tool System

## Architecture

```mermaid
classDiagram
    class BaseTool {
        <<abstract>>
        +name: str
        +description: str
        +parameters_schema: dict
        +to_definition() ToolDefinition
        +execute(**kwargs) str
    }
    class WebSearchTool {
        +name = "web_search"
        +execute(query) str
        -_search_tavily(query) list
        -_format_results(results) str
        -_synthesize(query, results_text) str
    }
    class ToolRegistry {
        -_tools: dict
        +register(tool)
        +get(name) BaseTool
        +get_definitions() list~ToolDefinition~
        +has_tools() bool
    }
    BaseTool <|-- WebSearchTool
    ToolRegistry o-- BaseTool
```

## Web Search Flow

```mermaid
graph TD
    A[LLM calls web_search tool] --> B[WebSearchTool.execute]
    B --> C[1. Call Tavily API]
    C --> D[Get top N search results]
    D --> E[2. Format results into text]
    E --> F[3. Call synthesis LLM]
    F --> G[gemini-2.5-flash summarizes results]
    G --> H[Return summary with citations]
    H --> I[Summary returned to main LLM]

    C -->|Error| J[Return error message]
    F -->|Synthesis fails| K[Return raw formatted results]
```

## Tool Registration

The `get_tool_registry()` singleton auto-registers tools based on available configuration:

```mermaid
graph TD
    A[get_tool_registry called] --> B{Already initialized?}
    B -->|Yes| C[Return cached registry]
    B -->|No| D[Create new ToolRegistry]
    D --> E{TAVILY_API_KEY set?}
    E -->|Yes| F[Register WebSearchTool]
    E -->|No| G[Skip web search]
    F --> H[Return registry]
    G --> H
```

## Files

| File | Purpose |
|------|---------|
| `backend/app/tools/__init__.py` | Package exports |
| `backend/app/tools/base.py` | `BaseTool` abstract class |
| `backend/app/tools/registry.py` | `ToolRegistry` + `get_tool_registry()` singleton |
| `backend/app/tools/web_search.py` | Tavily search + LLM synthesis |

## Configuration

| Setting | Default | Description |
|---------|---------|-------------|
| `TAVILY_API_KEY` | (empty) | Tavily API key. If not set, web search is disabled. |
| `WEB_SEARCH_MAX_RESULTS` | 5 | Number of search results to fetch |
| `WEB_SEARCH_SYNTHESIS_MODEL` | `gemini-1.5-flash` | LLM model used to synthesize search results |

## Adding a New Tool

1. Create a new class extending `BaseTool` in `backend/app/tools/`
2. Define `name`, `description`, and `parameters_schema` (JSON Schema)
3. Implement `async def execute(self, **kwargs) -> str`
4. Register in `get_tool_registry()` in `backend/app/tools/registry.py`
5. Add display mapping in `frontend/src/components/chat/ToolStatusIndicator.tsx`
