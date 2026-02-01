# Alfred AI Assistant

A personal AI assistant built with LangGraph, FastAPI, React, and Slack integration.

## Quick Start

### Prerequisites
- Docker and Docker Compose
- Node.js 20+ (for frontend development)
- Python 3.11+ (for backend development)
- [UV](https://docs.astral.sh/uv/) (Python package manager)

### Development

Start all services:
```bash
docker-compose -f docker-compose.dev.yml up
```

Access:
- Frontend: http://localhost:3000
- Backend API: http://localhost:8000
- API Docs: http://localhost:8000/docs

### Project Structure

```
alfred-pa/
├── backend/          # FastAPI + LangGraph backend
├── frontend/         # React + Tailwind frontend
├── docker-compose.yml
└── docker-compose.dev.yml
```

See [CLAUDE.md](./CLAUDE.md) for development guidelines and coding standards.

## License

Private - All rights reserved
