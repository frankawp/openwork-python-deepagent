# Dev Container for Linux Sandbox (nsjail)

This dev container is intended for macOS/Windows hosts that need a Linux runtime to test `NsjailSandbox`.

## What it includes

- Ubuntu 24.04 base
- Python 3 + venv tooling
- Node.js 20 + npm/corepack
- `uv` package manager
- `nsjail` built from source

## Required runtime flags

The container runs with:

- `--privileged`
- `--cap-add=SYS_ADMIN`
- `--security-opt=seccomp=unconfined`

These are required for namespace/chroot/mount operations used by nsjail.

## First run

1. Open the repo in VS Code.
2. Run **Dev Containers: Reopen in Container**.
3. Wait for `postCreate.sh` to finish (`npm install`, `uv sync`).

## Server config recommendation

In `server/config.yaml`:

- Set `sandbox.allow_local_fallback: false` to enforce Linux nsjail behavior.
- Keep `sandbox.enabled: true`.

If nsjail is unavailable, server startup will fail instead of silently falling back to local execution.
