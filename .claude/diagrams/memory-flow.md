# Memory System Flow

## Overview

The memory system provides long-term personalization by:
1. Storing user facts, preferences, and conversation summaries
2. Retrieving relevant memories via semantic search during conversations
3. Allowing manual saves via `/remember` command or natural language

## Manual Save Flow

```mermaid
graph TD
    A[User Message] --> B{Detect /remember or natural language}
    B -->|/remember I prefer dark mode| C[Extract content]
    B -->|remember that I work at...| C
    B -->|Regular message| D[Normal conversation flow]
    C --> E[Infer memory type]
    E --> F[Generate embedding via bge-base-en-v1.5]
    F --> G{Check for duplicates}
    G -->|Similar memory exists| H[Return existing memory note]
    G -->|New memory| I[Store in pgvector]
    I --> J[Confirm to user]
```

## Scheduled Extraction Flow

```mermaid
graph TD
    A[Scheduled Task Runs] --> B[Get users with new sessions]
    B --> C[For each user: get sessions since last extraction]
    C --> D[Format conversation messages]
    D --> E[Send to LLM with extraction prompt]
    E --> F[Parse JSON response]
    F --> G[For each extracted memory]
    G --> H[Generate embedding]
    H --> I{Check for duplicates}
    I -->|Duplicate| J[Skip]
    I -->|New| K[Store in pgvector]
```

## Retrieval Flow

```mermaid
graph TD
    A[New user message] --> B[Generate query embedding]
    B --> C[Cosine similarity search via pgvector]
    C --> D[Return top-5 similar memories]
    D --> E[Inject into system prompt]
    E --> F[LLM generates personalized response]
```

## Memory Types

| Type | Description | Examples |
|------|-------------|----------|
| **preference** | Things user likes/dislikes, settings | "Prefers dark mode", "Likes concise responses" |
| **knowledge** | Personal facts about the user | "Works at Acme Corp", "Lives in San Francisco" |
| **summary** | Key decisions or outcomes | "Decided to use React for frontend" |

## Technical Details

- **Embedding Model**: BAAI/bge-base-en-v1.5 (768 dimensions, local)
- **Vector Storage**: PostgreSQL with pgvector extension
- **Search Method**: Cosine similarity (top-5 results)
- **Deduplication Threshold**: 0.7 similarity (configurable)

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/memories` | List user's memories (paginated, filterable) |
| GET | `/api/memories/{id}` | Get specific memory |
| POST | `/api/memories` | Create a memory manually |
| PUT | `/api/memories/{id}` | Update memory content |
| DELETE | `/api/memories/{id}` | Delete a memory |

## Status

✅ **Complete** - Implemented in Phase 4
