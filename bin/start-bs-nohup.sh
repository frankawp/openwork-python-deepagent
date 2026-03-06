#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SERVER_DIR="$ROOT_DIR/server"
WEB_DIR="$ROOT_DIR/web"

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

start_backend() {
  if [[ ! -x "$SERVER_DIR/venv/bin/uvicorn" ]]; then
    echo "Backend venv missing: $SERVER_DIR/venv/bin/uvicorn"
    echo "Please set up backend dependencies first."
    exit 1
  fi

  if ! cleanup_stale_pid_file "$BACKEND_PID_FILE"; then
    echo "Backend already running (PID $(cat "$BACKEND_PID_FILE"))."
    return 0
  fi

  (
    cd "$SERVER_DIR"
    nohup ./venv/bin/uvicorn app.main:app --host "$BACKEND_HOST" --port "$BACKEND_PORT" >"$BACKEND_LOG" 2>&1 &
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
  echo "Backend started: PID $pid"
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

  (
    cd "$WEB_DIR"
    nohup npm run dev -- --host "$FRONTEND_HOST" --port "$FRONTEND_PORT" >"$FRONTEND_LOG" 2>&1 &
    echo $! >"$FRONTEND_PID_FILE"
  )

  sleep 1
  local pid
  pid="$(cat "$FRONTEND_PID_FILE")"
  if ! is_pid_running "$pid"; then
    echo "Frontend failed to start. Log: $FRONTEND_LOG"
    tail -n 40 "$FRONTEND_LOG" || true
    exit 1
  fi
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
