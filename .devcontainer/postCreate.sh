#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${REPO_ROOT}"

if [ -f package-lock.json ]; then
  npm install
fi

if [ -f server/pyproject.toml ]; then
  cd server
  if [ ! -d .venv ]; then
    uv venv .venv
  fi
  uv sync
fi
