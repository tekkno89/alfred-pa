# Agent Conversation Flow

## Flow Diagram

```mermaid
graph TD
    A[User Message Received] --> B[Initialize AgentState]
    B --> C[1. process_message]
    C --> D[Validate input]
    D --> E[Generate message IDs]
    E --> F[2. retrieve_context]
    F --> G[Get recent messages from DB]
    G --> H[Get memories - Phase 4]
    H --> I[3. generate_response]
    I --> J[Build prompt with system message]
    J --> K[Add conversation history]
    K --> L[Call LLM provider]
    L --> M[4. extract_memories]
    M --> N[Placeholder - Phase 4]
    N --> O[5. save_messages]
    O --> P[Save user message to DB]
    P --> Q[Save assistant response to DB]
    Q --> R[Return Response]
```

## State Fields

- `session_id`: Current session
- `user_id`: Current user
- `user_message`: Input from user
- `context_messages`: Recent history
- `memories`: Long-term memories
- `response`: Generated response
- `error`: Error if any step fails
