# openwork

openwork is a browser-based agent workspace for running long-lived AI tasks against real files, tools, and MCP services.

It gives each conversation its own isolated Daytona sandbox, then layers a web UI on top for chat, workspace browsing, task tracking, skill management, and MCP management.

![Agent workspace](docs/openwork-agent-bs.png)

![Skills and MCP management](docs/openwork-skills-mcp-bs.png)

> [!CAUTION]
> openwork can read files, execute tools, and connect to external services. Use it only with workspaces, credentials, and MCP servers you trust.

## What openwork is for

- running agent sessions against a real working directory instead of a toy chat box
- giving each thread an isolated sandboxed workspace
- attaching reusable skills and MCP servers to the agent
- reviewing files, outputs, tasks, and subagent activity in one browser interface
- keeping the control plane in a standard web deployment model

## Product shape

openwork is now a pure browser-server application:

- `web/`: React + Vite browser UI
- `server/`: FastAPI backend, auth, threads, models, skills, MCP, Daytona orchestration
- `docs/`: architecture notes and screenshots

There is no Electron runtime in the current product.

## How it works

```text
Browser UI
    |
    | HTTP + SSE
    v
FastAPI backend
    |
    | Daytona SDK
    v
Per-thread Daytona sandbox
```

At runtime:

1. A user opens or creates a thread.
2. The backend provisions or reconnects a Daytona sandbox for that thread.
3. The agent runs inside that sandbox and streams events back to the browser.
4. Skills and MCP servers are attached as agent capabilities.
5. Files, tasks, outputs, and agent responses stay visible in the same session UI.

## Core capabilities

- authenticated thread-based agent sessions
- streaming chat and tool execution updates over SSE
- workspace file browsing and preview
- user-managed skills
- user-managed MCP servers
- per-thread sandbox provisioning from Daytona
- support for snapshot-based sandboxes
- approval, interrupt, and resume flows for agent actions

## Quick start

### Prerequisites

- Node.js 20+
- npm 10+
- Python 3.11+
- `uv`
- MySQL
- Daytona account and API credentials

### 1. Configure the backend

```bash
cd server
cp .env.example .env
```

Set at least these values in `server/.env`:

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

Then start the backend:

```bash
cd server
uv sync
alembic upgrade head
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### 2. Start the web UI

```bash
cd web
npm install
npm run dev
```

Open [http://127.0.0.1:5173](http://127.0.0.1:5173).

## Day-to-day commands

```bash
# Build the browser UI
npm run build:web

# Run backend tests
npm run test:server
```

## Configuration notes

- `DAYTONA_SNAPSHOT` is optional. Leave it empty if new threads should start from the default image.
- Skills and MCP definitions are stored in the backend database.
- Agent execution still happens inside Daytona sandboxes, not inside the browser process.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

MIT. See [LICENSE](LICENSE).
