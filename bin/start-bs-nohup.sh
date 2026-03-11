#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SERVER_DIR="$ROOT_DIR/server"
WEB_DIR="$ROOT_DIR/web"

load_env_file() {
  local env_file="$1"
  if [[ ! -f "$env_file" ]]; then
    return 0
  fi

  set -a
  # shellcheck disable=SC1090
  source "$env_file"
  set +a
}

load_env_file "$SERVER_DIR/.env"

BACKEND_HOST="${BACKEND_HOST:-0.0.0.0}"
BACKEND_PORT="${BACKEND_PORT:-8000}"
FRONTEND_HOST="${FRONTEND_HOST:-0.0.0.0}"
FRONTEND_PORT="${FRONTEND_PORT:-5173}"

RUN_DIR="${OPENWORK_RUN_DIR:-$ROOT_DIR/.run}"
mkdir -p "$RUN_DIR"

BACKEND_PID_FILE="$RUN_DIR/backend.pid"
FRONTEND_PID_FILE="$RUN_DIR/frontend.pid"
BACKEND_LOG="$RUN_DIR/backend.log"
FRONTEND_LOG="$RUN_DIR/frontend.log"
BACKEND_PYTHON=""
BACKEND_STARTED_THIS_RUN=0

resolve_backend_python() {
  local candidates=(
    "$SERVER_DIR/.venv/bin/python"
  )

  local candidate
  for candidate in "${candidates[@]}"; do
    if [[ -x "$candidate" ]] && "$candidate" -c "import uvicorn" >/dev/null 2>&1; then
      BACKEND_PYTHON="$candidate"
      return 0
    fi
  done

  return 1
}

is_pid_running() {
  local pid="$1"
  [[ -n "$pid" ]] && kill -0 "$pid" >/dev/null 2>&1
}

cleanup_stale_pid_file() {
  local pid_file="$1"
  if [[ ! -f "$pid_file" ]]; then
    return 0
  fi
  local pid
  pid="$(cat "$pid_file" 2>/dev/null || true)"
  if [[ -n "$pid" ]] && is_pid_running "$pid"; then
    return 1
  fi
  rm -f "$pid_file"
  return 0
}

stop_backend_if_started_here() {
  if [[ "$BACKEND_STARTED_THIS_RUN" -ne 1 ]]; then
    return 0
  fi
  if [[ ! -f "$BACKEND_PID_FILE" ]]; then
    return 0
  fi
  local pid
  pid="$(cat "$BACKEND_PID_FILE" 2>/dev/null || true)"
  if [[ -n "$pid" ]] && is_pid_running "$pid"; then
    kill "$pid" >/dev/null 2>&1 || true
    sleep 0.5
    if is_pid_running "$pid"; then
      kill -9 "$pid" >/dev/null 2>&1 || true
    fi
  fi
  rm -f "$BACKEND_PID_FILE"
  echo "Stopped backend due to frontend startup failure."
}

start_backend() {
  if ! resolve_backend_python; then
    echo "No usable backend venv found under:"
    echo "  - $SERVER_DIR/.venv/bin/python"
    echo "Please set up backend dependencies first (for example: cd server && uv sync)."
    exit 1
  fi

  if ! cleanup_stale_pid_file "$BACKEND_PID_FILE"; then
    echo "Backend already running (PID $(cat "$BACKEND_PID_FILE"))."
    return 0
  fi

  (
    cd "$SERVER_DIR"
    nohup "$BACKEND_PYTHON" -m uvicorn app.main:app --host "$BACKEND_HOST" --port "$BACKEND_PORT" >"$BACKEND_LOG" 2>&1 &
    echo $! >"$BACKEND_PID_FILE"
  )

  sleep 1
  local pid
  pid="$(cat "$BACKEND_PID_FILE")"
  if ! is_pid_running "$pid"; then
    echo "Backend failed to start. Log: $BACKEND_LOG"
    tail -n 40 "$BACKEND_LOG" || true
    exit 1
  fi
  BACKEND_STARTED_THIS_RUN=1
  echo "Backend started: PID $pid"
}

launch_frontend() {
  (
    cd "$WEB_DIR"
    nohup npm run dev -- --host "$FRONTEND_HOST" --port "$FRONTEND_PORT" >"$FRONTEND_LOG" 2>&1 &
    echo $! >"$FRONTEND_PID_FILE"
  )

  sleep 1
  local pid
  pid="$(cat "$FRONTEND_PID_FILE")"
  is_pid_running "$pid"
}

start_frontend() {
  if ! command -v npm >/dev/null 2>&1; then
    echo "npm not found in PATH."
    exit 1
  fi

  if [[ ! -f "$WEB_DIR/package.json" ]]; then
    echo "Missing frontend project: $WEB_DIR/package.json"
    exit 1
  fi

  if ! cleanup_stale_pid_file "$FRONTEND_PID_FILE"; then
    echo "Frontend already running (PID $(cat "$FRONTEND_PID_FILE"))."
    return 0
  fi

  if ! launch_frontend; then
    if grep -q 'Host version ".*" does not match binary version ".*"' "$FRONTEND_LOG"; then
      echo "Detected esbuild binary mismatch, running npm rebuild esbuild and retrying..."
      (
        cd "$WEB_DIR"
        npm rebuild esbuild >>"$FRONTEND_LOG" 2>&1
      )
      rm -f "$FRONTEND_PID_FILE"
      if ! launch_frontend; then
        echo "Frontend failed to start after rebuild. Log: $FRONTEND_LOG"
        tail -n 40 "$FRONTEND_LOG" || true
        stop_backend_if_started_here
        exit 1
      fi
    else
      echo "Frontend failed to start. Log: $FRONTEND_LOG"
      tail -n 40 "$FRONTEND_LOG" || true
      stop_backend_if_started_here
      exit 1
    fi
  fi
  local pid
  pid="$(cat "$FRONTEND_PID_FILE")"
  echo "Frontend started: PID $pid"
}

start_backend
start_frontend

echo ""
echo "Openwork services started with nohup."
echo "Frontend: http://localhost:$FRONTEND_PORT"
echo "Backend:  http://localhost:$BACKEND_PORT"
echo "Backend log:  $BACKEND_LOG"
echo "Frontend log: $FRONTEND_LOG"
echo "Backend PID file:  $BACKEND_PID_FILE"
echo "Frontend PID file: $FRONTEND_PID_FILE"
