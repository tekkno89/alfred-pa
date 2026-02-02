# Architecture Overview

## Flow Diagram

```mermaid
graph TD
    A[React Webapp] --> B[FastAPI Backend]
    C[Slack Bot] --> B
    B --> D[Sessions API]
    B --> E[Auth API]
    D --> F[AlfredAgent]
    F --> G[Agent Nodes]
    G --> H[LLM Provider]
    H --> I[Vertex AI Gemini]
    H --> J[Vertex AI Claude]
    H --> K[OpenRouter]
    F --> L[PostgreSQL + pgvector]
    F --> M[Redis Cache]
```

## Components

- **React Webapp**: Main UI on port 5173
- **Slack Bot**: Thread-based conversations
- **FastAPI Backend**: API layer on port 8000
- **AlfredAgent**: LangGraph conversation handler
- **LLM Providers**: Gemini, Claude, or OpenRouter models
- **PostgreSQL**: Primary database with vector search
- **Redis**: Session caching
