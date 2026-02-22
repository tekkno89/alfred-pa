# Architecture Overview

## Flow Diagram

```mermaid
graph TD
    A[React Webapp] --> B[FastAPI Backend]
    C[Slack] -->|Events API| B
    B --> D[Sessions API]
    B --> E[Auth API]
    B --> S[Slack API]
    B --> DA[Dashboard API]
    B --> AD[Admin API]
    DA --> BART[BART API]
    D --> F[AlfredAgent]
    S --> F
    F --> G[ReAct Loop]
    G --> H[LLM Provider]
    G -->|tool calls| T[Tool Registry]
    T --> WS[Web Search Tool]
    WS --> TV[Tavily API]
    WS -->|synthesis| H2[Synthesis LLM]
    H --> I[Vertex AI Gemini]
    H --> J[Vertex AI Claude]
    H --> K[OpenRouter]
    F --> L[PostgreSQL + pgvector]
    S --> M[Redis]
    DA -->|cache| M
    D -->|Cross-sync| C
```

## Components

- **React Webapp**: Main UI on port 3000, includes Settings page for Slack linking
- **Slack**: Bi-directional integration via Events API and slash commands
- **FastAPI Backend**: API layer on port 8000
- **Sessions API**: Chat sessions with cross-sync to Slack threads
- **Auth API**: JWT auth + Slack account linking endpoints
- **Slack API**: Event handlers, slash commands, message posting
- **AlfredAgent**: LangGraph conversation handler
- **ReAct Loop**: Tool-calling loop — LLM generates response, optionally calls tools, feeds results back (max 3 iterations)
- **Tool Registry**: Singleton registry that auto-registers tools based on available API keys
- **Web Search Tool**: Tavily search + LLM synthesis (returns concise summary to main agent)
- **LLM Providers**: Gemini, Claude, or OpenRouter models
- **PostgreSQL**: Primary database with vector search
- **Dashboard API**: Dashboard preferences, feature access, BART proxy endpoints
- **Admin API**: User role management, feature access control (admin-only)
- **BART API**: Real-time train departure data from `api.bart.gov`, cached in Redis (30s departures, 24h stations)
- **Redis**: Event deduplication, linking codes (TTL-based), BART API cache
