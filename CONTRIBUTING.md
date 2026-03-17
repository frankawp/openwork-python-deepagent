# Contributing to openwork

openwork is now a browser-server application:

- `server/`: FastAPI backend, Daytona integration, persistence, agent runtime
- `web/`: React + Vite frontend

## Development setup

### Prerequisites

- Node.js 20+
- npm 10+
- Python 3.11+
- `uv`
- Git

### Local run

```bash
# Backend
cd server
cp .env.example .env
uv sync
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Frontend
cd web
npm install
npm run dev
```

## Project structure

```text
openwork/
├── server/
│   ├── app/
│   ├── alembic/
│   ├── scripts/
│   └── tests/
├── web/
│   ├── src/
│   └── public/
└── docs/
```

## Validation

```bash
# Frontend build
cd web
npm run build

# Backend tests
cd server
uv run python -m unittest
```

## Pull requests

1. Branch from `main`
2. Keep commits focused
3. Make sure the frontend builds and backend tests pass
4. Describe behavioral changes, especially API, sandbox, skill, or MCP changes
