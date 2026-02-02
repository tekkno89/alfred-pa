# Phase 4: Memory System

**Status:** ✅ Complete

## Overview

Long-term memory capabilities for Alfred enabling personalized conversations through:
- Semantic memory retrieval via pgvector
- Manual memory saves via `/remember` command
- Scheduled background extraction from conversations
- Memory CRUD API for user management

## Key Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Embedding model | bge-base-en-v1.5 (local, 768 dims) | No API costs, fast, good quality |
| Extraction timing | Scheduled background task | No conversation latency |
| Manual save | /remember + natural language | Maximum flexibility |
| Deduplication | 0.7 similarity threshold | Prevent near-duplicates |

## Implementation

### Database Migration
- [x] `002_memory_vector_768.py` - Changed embedding dimension from 1536 to 768

### Embedding Provider
- [x] `app/core/embeddings.py` - LocalEmbeddingProvider using sentence-transformers
- [x] Lazy model loading (only loads when first used)
- [x] Single text and batch embedding methods

### Memory Repository
- [x] `app/db/repositories/memory.py` - Full CRUD operations
- [x] Semantic search via pgvector cosine similarity
- [x] Duplicate detection for deduplication
- [x] Last extraction time tracking

### Agent Integration
- [x] Updated `retrieve_context` to search and inject memories
- [x] Added `/remember` command detection in `process_message`
- [x] Natural language save patterns (remember that, note that, etc.)
- [x] `handle_remember_command` for immediate saves with confirmation

### API Endpoints
- [x] `GET /api/memories` - List with pagination and type filter
- [x] `GET /api/memories/{id}` - Get single memory
- [x] `POST /api/memories` - Create with auto-embedding
- [x] `PUT /api/memories/{id}` - Update with re-embedding
- [x] `DELETE /api/memories/{id}` - Delete memory

### Scheduled Extraction
- [x] `app/tasks/extract_memories.py` - Background extraction task
- [x] LLM-based extraction with structured JSON output
- [x] Deduplication against existing memories
- [x] Run via: `python -m app.tasks.extract_memories`

### Configuration
- [x] `embedding_model` setting (default: BAAI/bge-base-en-v1.5)
- [x] `memory_retrieval_limit` setting (default: 5)
- [x] `memory_similarity_threshold` setting (default: 0.7)

## Files Created

| File | Purpose |
|------|---------|
| `alembic/versions/002_memory_vector_768.py` | Vector dimension migration |
| `app/core/embeddings.py` | Local embedding provider |
| `app/db/repositories/memory.py` | Memory repository |
| `app/schemas/memory.py` | API schemas |
| `app/api/memories.py` | REST endpoints |
| `app/tasks/__init__.py` | Tasks package |
| `app/tasks/extract_memories.py` | Extraction task |
| `tests/unit/test_embeddings.py` | Embedding + intent tests |
| `tests/unit/test_memory_repository.py` | Repository tests |
| `tests/integration/test_memories_api.py` | API tests |

## Files Modified

| File | Changes |
|------|---------|
| `app/db/models/memory.py` | Vector(768) |
| `app/agents/nodes.py` | Memory retrieval + /remember |
| `app/agents/alfred.py` | Memory repo + remember flow |
| `app/agents/state.py` | Remember command fields |
| `app/core/config.py` | Memory settings |
| `pyproject.toml` | sentence-transformers dep |
| `app/db/repositories/__init__.py` | Export |
| `app/schemas/__init__.py` | Export |
| `app/api/__init__.py` | Router |

## Testing

```
91 tests passed
- 17 unit tests for embeddings/remember detection
- 13 unit tests for memory repository
- 17 integration tests for memories API
- 44 existing tests (all passing)
```

## Usage

### Manual Save
```
User: /remember I prefer concise responses
Alfred: Very good, sir. I shall remember that: "I prefer concise responses"

User: Remember that I work at Acme Corp
Alfred: Very good, sir. I shall remember that: "I work at Acme Corp"
```

### Automatic Retrieval
Memories are automatically retrieved and injected into context when relevant to the user's message.

### API
```bash
# List memories
curl -H "Authorization: Bearer $TOKEN" http://localhost:8000/api/memories

# Create memory
curl -X POST -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"type": "preference", "content": "Prefers dark mode"}' \
  http://localhost:8000/api/memories

# Run extraction task
docker-compose exec backend python -m app.tasks.extract_memories
```

## Future Enhancements

- [ ] Memory importance scoring
- [ ] Memory expiration/decay
- [ ] User-facing memory management UI (Phase 5)
- [ ] Memory categories/tags
- [ ] **Session summaries for search** - Generate and store summaries of each conversation session, enabling users to ask "when did we last talk about X?" or search for past conversations by topic. Could include:
  - Auto-generated session summary after conversation ends (or on session close)
  - Key topics/entities extracted and tagged
  - Timestamps and session links for easy navigation
  - Semantic search across session summaries
  - Related to memory categories/tags - summaries could be tagged with topics for faceted search
