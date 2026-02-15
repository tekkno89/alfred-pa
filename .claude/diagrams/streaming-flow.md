# SSE Streaming Flow

## Flow Diagram

```mermaid
graph TD
    A[Client opens SSE connection] --> B[FastAPI creates StreamingResponse]
    B --> C[event_stream generator starts]
    C --> D[AlfredAgent.stream called]
    D --> E{Tools available?}
    E -->|Yes| F[generate_response_stream_with_tools]
    E -->|No| G[generate_response_stream]
    F --> H[Build prompt messages]
    G --> H
    H --> I[Call LLM provider]
    I --> J{Response type?}
    J -->|Text token| K[Yield token event]
    K --> L[Send SSE: type=token]
    L --> I
    J -->|Tool call| M[Yield tool_use event]
    M --> N[Send SSE: type=tool_use]
    N --> O[Execute tool]
    O --> P[Append result to messages]
    P --> I
    J -->|Stream complete| Q[Collect full response]
    Q --> R[Save messages to DB]
    R --> S[Send SSE: type=done]
    S --> T[Close connection]
```

## SSE Event Types

| Event | Fields | Description |
|-------|--------|-------------|
| `token` | `content: string` | Response text chunk |
| `tool_use` | `tool_name: string` | Tool execution started (e.g., "web_search") |
| `done` | — | Stream complete, response saved |
| `error` | `content: string` | Error occurred |

## SSE Format

Each event sent as:
```
data: {"type":"token","content":"Hello"}\n\n
data: {"type":"tool_use","tool_name":"web_search"}\n\n
data: {"type":"done"}\n\n
```

## Frontend Handling

The `useChat` hook processes events:
- `token` → append to streaming message, clear `activeToolName`
- `tool_use` → set `activeToolName` (shows `ToolStatusIndicator`)
- `done` → finalize message, refetch session
- `error` → display error

The `ToolStatusIndicator` component maps tool names to display strings:
- `web_search` → "Searching the web..." with search icon
- Other tools → "Running {tool_name}..." with spinner
