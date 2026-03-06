#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUN_DIR="${OPENWORK_RUN_DIR:-$ROOT_DIR/.run}"

BACKEND_PORT="${BACKEND_PORT:-8000}"
FRONTEND_PORT="${FRONTEND_PORT:-5173}"

BACKEND_PID_FILE="$RUN_DIR/backend.pid"
FRONTEND_PID_FILE="$RUN_DIR/frontend.pid"

is_pid_running() {
  local pid="$1"
  [[ -n "$pid" ]] && kill -0 "$pid" >/dev/null 2>&1
}

stop_pid() {
  local name="$1"
  local pid="$2"

  if ! is_pid_running "$pid"; then
    echo "$name already stopped (PID $pid not running)."
    return 0
  fi

  kill "$pid" >/dev/null 2>&1 || true
  for _ in {1..10}; do
    if ! is_pid_running "$pid"; then
      echo "$name stopped: PID $pid"
      return 0
    fi
    sleep 0.3
  done

  kill -9 "$pid" >/dev/null 2>&1 || true
  if ! is_pid_running "$pid"; then
    echo "$name force-stopped: PID $pid"
    return 0
  fi

  echo "Failed to stop $name PID $pid"
  return 1
}

stop_from_pid_file() {
  local name="$1"
  local pid_file="$2"
  local failed=0

  if [[ ! -f "$pid_file" ]]; then
    echo "$name pid file not found: $pid_file"
    return 0
  fi

  local pid
  pid="$(cat "$pid_file" 2>/dev/null || true)"
  if [[ -z "$pid" ]]; then
    echo "$name pid file is empty: $pid_file"
    rm -f "$pid_file"
    return 0
  fi

  if ! stop_pid "$name" "$pid"; then
    failed=1
  fi
  rm -f "$pid_file"
  return "$failed"
}

stop_by_port() {
  local name="$1"
  local port="$2"
  local pids

  pids="$(lsof -tiTCP:"$port" -sTCP:LISTEN 2>/dev/null || true)"
  if [[ -z "$pids" ]]; then
    echo "$name no listener on port $port"
    return 0
  fi

  echo "$name fallback: stopping listeners on port $port ($pids)"
  local failed=0
  for pid in $pids; do
    if ! stop_pid "$name" "$pid"; then
      failed=1
    fi
  done
  return "$failed"
}

mkdir -p "$RUN_DIR"

backend_failed=0
frontend_failed=0

if ! stop_from_pid_file "Backend" "$BACKEND_PID_FILE"; then
  backend_failed=1
fi
if ! stop_from_pid_file "Frontend" "$FRONTEND_PID_FILE"; then
  frontend_failed=1
fi

if ! stop_by_port "Backend" "$BACKEND_PORT"; then
  backend_failed=1
fi
if ! stop_by_port "Frontend" "$FRONTEND_PORT"; then
  frontend_failed=1
fi

if [[ "$backend_failed" -eq 0 && "$frontend_failed" -eq 0 ]]; then
  echo "Openwork services stopped."
  exit 0
fi

echo "Some services may not have stopped cleanly."
exit 1
