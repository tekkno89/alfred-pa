# LLM Provider Selection

## Flow Diagram

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
- `claude-3-5-sonnet@20240620` → VertexClaudeProvider
- `openrouter/anthropic/claude-3.5-sonnet` → OpenRouterProvider
