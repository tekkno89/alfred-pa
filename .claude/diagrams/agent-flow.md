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
    O --> P{Tools available?}
    P -->|Yes| Q[3a. ReAct Loop]
    P -->|No| R[3b. generate_response]
    Q --> S[Build prompt with system + memories + date]
    R --> S
    S --> T[Call LLM provider]
    T --> U{Tool calls in response?}
    U -->|Yes| V[Execute tools]
    V --> W[Append tool results to messages]
    W --> X{Max iterations reached?}
    X -->|No| T
    X -->|Yes| Y[Force text response via _build_final_messages]
    U -->|No| Z[Text response received]
    Y --> Z
    Z --> AA[4. extract_memories - scheduled task]
    AA --> BB[5. save_messages]
    BB --> CC[Save user message to DB]
    CC --> DD[Save assistant response to DB]
    DD --> EE[Return Response]
    K --> BB
```

## ReAct Loop Detail

```mermaid
graph TD
    A[Start ReAct Loop] --> B[Iteration 1]
    B --> C[Call LLM with tools]
    C --> D{Response type?}
    D -->|Text only| E[Return text response]
    D -->|Tool calls| F[Emit tool_use SSE event]
    F --> G[Execute tool]
    G --> H[Append tool result to messages]
    H --> I{Iteration < MAX?}
    I -->|Yes| J[Next iteration]
    J --> C
    I -->|No, iteration = MAX| K[Build final messages]
    K --> L[Strip tool messages, inject results into system prompt]
    L --> M[Call LLM without tools]
    M --> E
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

## Tool Execution

When the LLM requests a tool call:
1. Tool registry looks up the tool by name
2. Tool executes with provided arguments
3. Result is appended to conversation as a tool message
4. LLM is called again with the updated conversation
5. Process repeats until the LLM responds with text (max 3 iterations)

On the final iteration, tool messages are collapsed into the system prompt
and the LLM is called without tools to force a text response.
