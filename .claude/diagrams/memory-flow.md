# Memory System Flow

## Extraction Flow (Phase 4)

```mermaid
graph TD
    A[Conversation Complete] --> B[Analyze for memorable facts]
    B --> C[Classify memory type]
    C --> D[Preference - user likes dark mode]
    C --> E[Knowledge - user works at Acme]
    C --> F[Summary - discussed timeline]
    D --> G[Generate embedding via LLM]
    E --> G
    F --> G
    G --> H[Store in pgvector]
```

## Retrieval Flow (Phase 4)

```mermaid
graph TD
    A[New user message] --> B[Generate query embedding]
    B --> C[Cosine similarity search]
    C --> D[Return top-K memories]
    D --> E[Add to system prompt]
    E --> F[Enhanced context for LLM]
```

## Memory Types

- **Preference**: UI settings, communication style
- **Knowledge**: Personal facts, work info
- **Summary**: Conversation summaries, decisions

## Current Status

Phase 2: Placeholder only - returns empty dict
Phase 4: Will implement full extraction and retrieval
