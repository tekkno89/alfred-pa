# Agent Conversation Flow

## Flow Diagram

```mermaid
graph TD
    A[User Message Received] --> B[Initialize AgentState]
    B --> C[1. process_message]
    C --> D[Validate input]
    D --> E[Detect /remember command]
    E --> F{Is remember command?}
    F -->|Yes| G[1b. handle_remember_command]
    G --> H[Generate embedding]
    H --> I[Check for duplicates]
    I --> J[Save memory to DB]
    J --> K[Return confirmation]
    F -->|No| L[2. retrieve_context]
    L --> M[Get recent messages from DB]
    M --> N[Generate query embedding]
    N --> O[Semantic search for memories]
    O --> P[3. generate_response]
    P --> Q[Build prompt with system + memories]
    Q --> R[Add conversation history]
    R --> S[Call LLM provider]
    S --> T[4. extract_memories - scheduled task]
    T --> U[5. save_messages]
    U --> V[Save user message to DB]
    V --> W[Save assistant response to DB]
    W --> X[Return Response]
    K --> U
```

## State Fields

| Field | Type | Description |
|-------|------|-------------|
| `session_id` | str | Current session ID |
| `user_id` | str | Current user ID |
| `user_message` | str | Input from user |
| `is_remember_command` | bool | Whether message is a /remember command |
| `remember_content` | str | Content to save (if remember command) |
| `context_messages` | list | Recent conversation history |
| `memories` | list | Retrieved long-term memories |
| `response` | str | Generated response |
| `error` | str | Error message if any step fails |

## Remember Command Detection

The agent detects save intent via:
- **Explicit command**: `/remember <content>`
- **Natural language patterns**:
  - "remember that..."
  - "please remember that..."
  - "save to memory: ..."
  - "note that..."
  - "keep in mind that..."

## Memory Retrieval

On each message (unless it's a /remember command):
1. Generate embedding for user's message using bge-base-en-v1.5
2. Query pgvector for top-5 semantically similar memories
3. Inject memories into system prompt as "Relevant context about the user"
