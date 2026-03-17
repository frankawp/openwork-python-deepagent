# openwork

openwork is a browser-server workspace for deep agents. It combines:

- a FastAPI backend for auth, threads, models, skills, MCP, and Daytona sandboxes
- a React frontend for chat, files, tasks, agents, and capability management
- a Daytona-backed execution model so each thread can work inside an isolated workspace

![Agent workspace](docs/openwork-agent-bs.png)

![Skills and MCP management](docs/openwork-skills-mcp-bs.png)

> [!CAUTION]
> openwork gives agents access to files, tools, and remote services. Review approvals carefully and only run against workspaces and MCP servers you trust.

## Architecture

```text
Browser UI (Vite/React)
        |
        | HTTP + SSE
        v
FastAPI backend
        |
        | Daytona SDK
        v
Per-thread Daytona sandbox
```

## Repository layout

```text
openwork/
├── server/   # FastAPI app, models, migrations, runtime, tests
├── web/      # React + Vite frontend
└── docs/     # Architecture notes and screenshots
```

## Prerequisites

- Node.js 20+
- npm 10+
- Python 3.11+
- `uv`
- MySQL
- Daytona account and API credentials

## Backend setup

```bash
cd server
cp .env.example .env
```

Fill at least these values in `server/.env`:

```dotenv
DATABASE_URL=mysql+pymysql://user:pass@host:3306/openwork
JWT_SECRET=CHANGE_ME
WORKSPACE_ROOT=/var/lib/openwork/workspaces
DATA_DIR=/var/lib/openwork
ADMIN_EMAIL=admin@example.com
ADMIN_PASSWORD=admin123
DAYTONA_API_KEY=
DAYTONA_API_URL=https://app.daytona.io/api
DAYTONA_TARGET=us
DAYTONA_SNAPSHOT=
```

Then install dependencies and start the server:

```bash
cd server
uv sync
alembic upgrade head
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

## Frontend setup

```bash
cd web
npm install
npm run dev
```

By default the frontend connects to `http://127.0.0.1:8000` in local development.

## What the system supports

- authenticated thread-based agent sessions
- SSE streaming responses
- tool approvals and interrupt/resume flows
- file browsing and file preview from the Daytona workspace
- user-managed skills
- user-managed MCP servers and per-thread MCP binding
- Daytona snapshot-based sandbox provisioning

## Useful commands

```bash
# Build the frontend
npm run build:web

# Run backend tests
npm run test:server
```

## Notes

- `DAYTONA_SNAPSHOT` is optional. Leave it empty if you do not want new threads to provision from a snapshot.
- MCP and skill state are persisted in the backend database; runtime execution still happens inside Daytona sandboxes.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

MIT. See [LICENSE](LICENSE).
