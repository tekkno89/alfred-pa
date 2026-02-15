# LLM Provider Abstraction

## Provider Selection

```mermaid
graph TD
    A[get_llm_provider called] --> B{model_name provided?}
    B -->|No| C[Use DEFAULT_LLM from settings]
    B -->|Yes| D[Use provided model_name]
    C --> E{Check model prefix}
    D --> E
    E -->|openrouter/*| F[Strip prefix]
    F --> G[Create OpenRouterProvider]
    E -->|gemini-*| H[Create VertexGeminiProvider]
    E -->|claude-*| I[Create VertexClaudeProvider]
    E -->|other| J[Default to VertexGeminiProvider]
    G --> K[Return LLMProvider]
    H --> K
    I --> K
    J --> K
```

## Model Examples

- `gemini-1.5-pro` → VertexGeminiProvider
- `gemini-2.5-flash` → VertexGeminiProvider (used for web search synthesis)
- `claude-3-5-sonnet@20240620` → VertexClaudeProvider
- `claude-opus-4-6@default` → VertexClaudeProvider
- `openrouter/anthropic/claude-3.5-sonnet` → OpenRouterProvider

## Provider Interface

```mermaid
classDiagram
    class LLMProvider {
        <<abstract>>
        +generate(messages, temperature, max_tokens) str
        +stream(messages, temperature, max_tokens) AsyncIterator~str~
        +generate_with_tools(messages, tools, temperature, max_tokens) LLMResponse
        +stream_with_tools(messages, tools, temperature, max_tokens) AsyncIterator~LLMResponse~
    }
    class OpenRouterProvider {
        -api_key: str
        -model_name: str
        +generate()
        +stream()
        +generate_with_tools()
        +stream_with_tools()
    }
    class VertexGeminiProvider {
        -project_id: str
        -location: str
        -model_name: str
        +generate()
        +stream()
        +generate_with_tools()
        +stream_with_tools()
    }
    class VertexClaudeProvider {
        -project_id: str
        -location: str
        -model_name: str
        +generate()
        +stream()
        +generate_with_tools()
        +stream_with_tools()
    }
    LLMProvider <|-- OpenRouterProvider
    LLMProvider <|-- VertexGeminiProvider
    LLMProvider <|-- VertexClaudeProvider
```

## Key Types

| Type | Description |
|------|-------------|
| `LLMMessage` | Message with role (system/user/assistant/tool), content, optional tool_calls and tool_call_id |
| `ToolDefinition` | Tool schema: name, description, JSON Schema parameters |
| `ToolCall` | Tool invocation: id, name, arguments dict |
| `LLMResponse` | Response containing text content and/or tool calls |

## Tool-Calling Flow

Each provider converts between its native format and the standardized types:

- **OpenRouter**: Uses OpenAI-compatible `tools` parameter and `tool_calls` response field
- **VertexGemini**: Uses LangChain `bind_tools()` on `ChatVertexAI`, parses `AIMessage.tool_calls`
- **VertexClaude**: Uses LangChain `bind_tools()` on `ChatAnthropicVertex`, handles content block format via `_extract_text_content()`

The `_extract_text_content()` helper normalizes Anthropic's content block format
(`[{"type": "text", "text": "..."}]`) to plain strings across all tool-calling methods.
