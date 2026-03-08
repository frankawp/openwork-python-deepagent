#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
STACK_DIR="${DAYTONA_LOCAL_STACK_DIR:-$ROOT_DIR/.run/daytona-local}"
DAYTONA_GIT_REF="${DAYTONA_GIT_REF:-main}"
DAYTONA_FORCE_REFRESH="${DAYTONA_FORCE_REFRESH:-0}"
PREPARE_ONLY=0
BASE_RAW_URL="https://raw.githubusercontent.com/daytonaio/daytona/${DAYTONA_GIT_REF}/docker"
COMPOSE_FILE="$STACK_DIR/docker-compose.yaml"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --prepare-only)
      PREPARE_ONLY=1
      shift
      ;;
    --force-refresh)
      DAYTONA_FORCE_REFRESH=1
      shift
      ;;
    --)
      shift
      break
      ;;
    *)
      echo "Unknown argument: $1" >&2
      echo "Usage: $0 [--prepare-only] [--force-refresh]" >&2
      exit 1
      ;;
  esac
done

mkdir -p "$STACK_DIR"

files=(
  "docker-compose.yaml"
  "dex/config.yaml"
  "pgadmin4/servers.json"
  "pgadmin4/pgpass"
  "otel/otel-collector-config.yaml"
)

for rel in "${files[@]}"; do
  dst="$STACK_DIR/$rel"
  if [[ "$DAYTONA_FORCE_REFRESH" != "1" && -s "$dst" ]]; then
    continue
  fi
  mkdir -p "$(dirname "$dst")"
  echo "Fetching $rel"
  curl -fsSL "$BASE_RAW_URL/$rel" -o "$dst"
done

if [[ "$PREPARE_ONLY" == "1" ]]; then
  echo "Daytona local stack files prepared at: $STACK_DIR"
  echo "Run server/scripts/daytona_local_up.sh to start containers."
  exit 0
fi

if ! command -v docker >/dev/null 2>&1; then
  echo "docker is required." >&2
  exit 1
fi

if docker compose version >/dev/null 2>&1; then
  COMPOSE_CMD=(docker compose)
elif command -v docker-compose >/dev/null 2>&1; then
  COMPOSE_CMD=(docker-compose)
else
  echo "docker compose (plugin or standalone) is required." >&2
  exit 1
fi

"${COMPOSE_CMD[@]}" -f "$COMPOSE_FILE" up -d

cat <<MSG

Daytona local stack is starting.

Stack directory:
  $STACK_DIR

Next steps:
1) Open Daytona Dashboard: http://localhost:3000/dashboard
2) Sign in with default local credentials:
   email: dev@daytona.io
   password: password
3) Create an API key in Dashboard.
4) Configure Openwork backend env (server/.env):
   DAYTONA_API_KEY=<your_local_daytona_api_key>
   DAYTONA_API_URL=http://localhost:3000/api
   DAYTONA_TARGET=us

If Openwork backend runs in devcontainer, use:
   DAYTONA_API_URL=http://host.docker.internal:3000/api

To stop the stack:
  server/scripts/daytona_local_down.sh
MSG
