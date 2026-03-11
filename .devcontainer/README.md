# Dev Container for Daytona Backend

This dev container is intended for macOS/Windows hosts that need a Linux runtime to run the Openwork backend with Daytona.

## What it includes

- Ubuntu 24.04 base
- Python 3 + venv tooling
- Node.js 20 + npm/corepack
- `uv` package manager
- Docker outside of Docker (use host Docker daemon via mounted socket)

## First run

1. Open the repo in VS Code.
2. Run **Dev Containers: Reopen in Container**.
3. Wait for `postCreate.sh` to finish (`npm install`, `uv sync`).
4. Rebuild container after config changes, then verify Docker is reachable:

```bash
docker version
docker ps
```

## Server config recommendation

In `server/config.yaml`:

- Keep `sandbox.enabled: true`.

In `server/.env`, configure Daytona credentials:

```bash
DAYTONA_API_KEY=...
DAYTONA_API_URL=https://app.daytona.io/api
DAYTONA_TARGET=us
```
