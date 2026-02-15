# Chat API Request Flow

## Flow Diagram

```mermaid
graph TD
    A[Client POST /sessions/id/messages] --> B[Validate JWT Token]
    B --> C[Get Session from DB]
    C --> D{Session exists?}
    D -->|No| E[Return 404]
    D -->|Yes| F{User authorized?}
    F -->|No| G[Return 403]
    F -->|Yes| H[Sync user message to Slack if applicable]
    H --> I[Create SSE StreamingResponse]
    I --> J[Create AlfredAgent]
    J --> K[agent.stream]
    K --> L[Process message]
    L --> M[Retrieve context]
    M --> N{Tools available?}
    N -->|Yes| O[ReAct loop with tools]
    N -->|No| P[Stream tokens from LLM]
    O --> Q{Event type?}
    Q -->|token| R[Send SSE token event]
    Q -->|tool_use| S[Send SSE tool_use event]
    S --> O
    R --> O
    P --> R2[Send SSE token event]
    R2 --> P
    O --> T[Stream complete]
    P --> T
    T --> U[Extract memories]
    U --> V[Save messages to DB]
    V --> W[Send SSE done event]
    W --> X[Cross-sync response to Slack if applicable]
```

## SSE Events

- `{"type": "token", "content": "..."}` - Response text chunk
- `{"type": "tool_use", "tool_name": "web_search"}` - Tool execution in progress
- `{"type": "done"}` - Stream complete
- `{"type": "error", "content": "..."}` - Error occurred
