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
    F -->|Yes| H[Create SSE StreamingResponse]
    H --> I[Create AlfredAgent]
    I --> J[agent.stream]
    J --> K[Process message]
    K --> L[Retrieve context]
    L --> M[Stream tokens from LLM]
    M --> N[Send SSE token event]
    N --> M
    M --> O[Stream complete]
    O --> P[Extract memories]
    P --> Q[Save messages to DB]
    Q --> R[Send SSE done event]
```

## SSE Events

- `{"type": "token", "content": "..."}` - Response chunk
- `{"type": "done"}` - Stream complete
- `{"type": "error", "content": "..."}` - Error occurred
