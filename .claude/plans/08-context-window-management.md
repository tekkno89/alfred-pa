# Phase 8: Context Window Management

**Status:** Not Started

## Overview

Replace the current hard-coded 10-message history limit with a token-aware hybrid approach: send the full conversation history until it reaches 80% of the model's context window, then summarize older messages and trim them from state. Database messages are never deleted — this only affects what gets sent to the LLM.

## Problem

- `retrieve_context_node` loads the last 10 messages via `get_recent_messages(limit=10)`
- This is message-count trimming — a 3-word message and a 2,000-word message cost the same "slot"
- In short conversations, we're potentially sending less context than we could
- In conversations with long messages, 10 messages might exceed what we can afford token-wise
- No summarization of older context — once a message falls outside the window, it's gone

## Goals

- Token-based context management instead of message-count
- Send full history when it fits within the context window
- When history exceeds 80% of context window, summarize older messages and keep recent ones
- Persist summaries on the session so we don't re-summarize on every request
- Never delete messages from the database

## Out of Scope

- Prompt caching (can be layered on separately)
- ReAct tool loop logic (iteration counting, max iterations, force-text behavior) — unchanged
- Frontend changes

**Note:** The graph structure will be simplified by removing the remember/memory paths (entry and exit), but the core ReAct cycle (`llm_node ↔ tool_node`) and its control logic remain untouched.

## Key Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Token counting | `tiktoken` (cl100k_base) | Fast, local, good approximation across models |
| Context threshold | 80% of model context window | Leave room for system prompt, tool definitions, and response |
| Summary storage | `conversation_summary` + `summary_through_id` on Session model | Persist across requests, avoid re-summarizing |
| Summarization model | Configurable, default to main `default_llm` | Summary quality matters — use a capable model to avoid losing important context |
| Summary approach | Incremental — extend existing summary | Avoids re-reading the full history each time |

## Architecture

### Current Flow
```
retrieve_context_node:
  1. SELECT last 10 messages FROM messages WHERE session_id = X
  2. Put them in state["context_messages"]

build_prompt_messages:
  1. System prompt
  2. context_messages (all 10)
  3. Current user message
```

### Proposed Flow
```
retrieve_context_node:
  1. Load session (includes conversation_summary and summary_through_id)
  2. SELECT all messages after summary_through_id (or all if no summary)
  3. Count tokens: system_prompt + summary + messages + user_message
  4. If under 80% threshold → use everything as-is
  5. If over 80% threshold:
     a. Call LLM to summarize oldest messages (extending existing summary)
     b. Update session.conversation_summary and session.summary_through_id
     c. Keep only recent messages that fit within budget

build_prompt_messages:
  1. System prompt
  2. If summary exists → inject: "Summary of earlier conversation: ..."
  3. Recent context_messages
  4. Current user message
```

## Implementation

### 1. Database Changes

- [ ] Add `conversation_summary` (Text, nullable) to Session model
- [ ] Add `summary_through_id` (UUID FK to messages, nullable) to Session model
- [ ] Create Alembic migration

### 2. Token Counting Utility

- [ ] Create `app/core/tokens.py`
- [ ] `count_tokens(text: str) -> int` — count tokens using tiktoken cl100k_base
- [ ] `get_context_limit(model_name: str) -> int` — return context window size for configured model
- [ ] Add model context window mapping (gemini-1.5-pro: 1M, claude-3.5-sonnet: 200K, etc.)
- [ ] Add `tiktoken` to dependencies

### 3. Summarization Function

- [ ] Create `app/core/summarize.py`
- [ ] `summarize_messages(messages, existing_summary=None) -> str`
- [ ] Uses the configured summarization model (defaults to `default_llm`)
- [ ] Prompt: condense these messages into a running summary, preserving key facts, decisions, and context
- [ ] If `existing_summary` provided, prompt says "extend this summary with the following new messages"

### 4. Update retrieve_context_node

- [ ] Load session with summary fields
- [ ] Load messages after `summary_through_id` (instead of last 10)
- [ ] If no summary, load all session messages
- [ ] Add `MessageRepository.get_messages_after(session_id, after_message_id)` method
- [ ] Count tokens for full prompt (system + summary + messages + user message)
- [ ] If under threshold: put all messages in `state["context_messages"]`, put summary in `state["conversation_summary"]`
- [ ] If over threshold: call `summarize_messages()`, update session in DB, trim state

### 5. Update build_prompt_messages

- [ ] Add `conversation_summary` to AgentState TypedDict
- [ ] If `state["conversation_summary"]` exists, add to system prompt: "Summary of earlier conversation:\n{summary}"
- [ ] Place it after the main system prompt but before tool usage instructions
- [ ] Remove memory injection from `build_prompt_messages` (memories not currently in use)

### 6. Remove Unused Memory Integration from Agent

- [ ] Remove memory retrieval from `retrieve_context_node` (embedding search, `memories` state field)
- [ ] Remove `/remember` command detection from `process_message_node`
- [ ] Remove `handle_remember_node` and `save_messages_node` from graph
- [ ] Remove remember-related routing in `route_after_process`
- [ ] Remove remember-related fields from `AgentState` (`is_remember_command`, `remember_content`, `memories`)
- [ ] Remove `extract_memories_node` placeholder from graph
- [ ] Simplify graph: `process_message → retrieve_context → save_user_message → llm_node → ...`
- [ ] Keep the memory DB model, repository, API endpoints, and embedding provider intact for future re-implementation
- [ ] Note: Natural language remember patterns, memory dedup, and memory injection will be re-implemented in a future phase

### 7. Configuration

- [ ] Add `context_usage_threshold: float = 0.8` to Settings
- [ ] Add `context_summary_model: str = ""` to Settings (empty = use `default_llm`)

### 8. Update Tests

- [ ] Test token counting utility
- [ ] Test summarization function
- [ ] Test retrieve_context_node with short conversations (no summary needed)
- [ ] Test retrieve_context_node with long conversations (triggers summarization)
- [ ] Test incremental summarization (extending existing summary)
- [ ] Test build_prompt_messages with and without summary
- [ ] Remove/update remember-related tests
- [ ] Update existing agent tests that mock `get_recent_messages`

## Files to Create

| File | Purpose |
|------|---------|
| `app/core/tokens.py` | Token counting and context limit utilities |
| `app/core/summarize.py` | Conversation summarization via LLM |
| `alembic/versions/XXX_add_session_summary.py` | Migration for summary fields |
| `tests/unit/test_tokens.py` | Token counting tests |
| `tests/unit/test_summarize.py` | Summarization tests |

## Files to Modify

| File | Changes |
|------|---------|
| `app/db/models/session.py` | Add `conversation_summary`, `summary_through_id` columns |
| `app/db/repositories/message.py` | Add `get_messages_after()` method |
| `app/agents/state.py` | Add `conversation_summary`, remove `is_remember_command`, `remember_content`, `memories` |
| `app/agents/nodes.py` | Update `retrieve_context_node`, `build_prompt_messages`, remove remember/memory nodes |
| `app/agents/graph.py` | Remove remember path, remove `extract_memories_node`, simplify routing |
| `app/core/config.py` | Add context threshold and summary model settings |
| `pyproject.toml` | Add `tiktoken` dependency |
| `tests/test_agent.py` | Update mocks, remove remember tests |

## Edge Cases

- **First message in session**: No history, no summary — works as today
- **Short conversations**: Under threshold, full history sent — no summarization overhead
- **Very long single message**: Could exceed budget on its own — need to handle gracefully (truncate or warn)
- **Summary + recent messages still over budget**: May need to trim recent messages too or re-summarize more aggressively
- **Model change mid-session**: Context window size changes — summary threshold adapts automatically since it's percentage-based
- **Slack cross-sync**: Messages from both sources are in the same session — summarization handles them the same way

## Verification

- [ ] Short conversation (<80% context): all messages sent, no summarization
- [ ] Long conversation (>80% context): summary generated, older messages trimmed from state, recent messages preserved
- [ ] Subsequent messages after summarization: summary loaded from session, only new messages queried
- [ ] Summary extends incrementally when threshold is hit again
- [ ] Database messages are never deleted
- [ ] Remember/memory code removed from agent graph without breaking anything
- [ ] Memory API endpoints still functional (for future re-implementation)
- [ ] Existing tests pass with updated mocks

## Future Enhancements

- [ ] Re-implement memory system (`/remember`, semantic retrieval, memory injection into prompt)
- [ ] Prompt caching for repeat system prompt / tool definitions
- [ ] Adaptive summarization aggressiveness based on conversation topic complexity
- [ ] Token counting per-model (model-specific tokenizers instead of cl100k_base approximation)
