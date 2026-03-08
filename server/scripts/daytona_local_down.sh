#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
STACK_DIR="${DAYTONA_LOCAL_STACK_DIR:-$ROOT_DIR/.run/daytona-local}"
COMPOSE_FILE="$STACK_DIR/docker-compose.yaml"
REMOVE_VOLUMES=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --volumes)
      REMOVE_VOLUMES=1
      shift
      ;;
    *)
      echo "Unknown argument: $1" >&2
      echo "Usage: $0 [--volumes]" >&2
      exit 1
      ;;
  esac
done

if [[ ! -f "$COMPOSE_FILE" ]]; then
  echo "Compose file not found: $COMPOSE_FILE"
  echo "Nothing to stop."
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

if [[ "$REMOVE_VOLUMES" == "1" ]]; then
  "${COMPOSE_CMD[@]}" -f "$COMPOSE_FILE" down --volumes
  echo "Daytona local stack stopped and volumes removed."
else
  "${COMPOSE_CMD[@]}" -f "$COMPOSE_FILE" down
  echo "Daytona local stack stopped."
fi
