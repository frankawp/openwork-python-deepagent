from __future__ import annotations

import datetime as dt
import hashlib
import json
import re
import shlex
import time
from typing import Any

import httpx
from sqlalchemy import Select, select
from sqlalchemy.orm import Session, joinedload

from .crypto import decrypt, encrypt
from .models import MCPServer, Thread, ThreadMCPBinding, ThreadMCPRuntimeState

MCP_KEY_PATTERN = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,62}[a-z0-9])?$")
MCP_TRANSPORTS = {"streamable_http", "sse", "stdio"}

STATUS_DIRTY = "dirty"
STATUS_CONNECTING = "connecting"
STATUS_READY = "ready"
STATUS_FAILED = "failed"
VALID_STATUSES = {STATUS_DIRTY, STATUS_CONNECTING, STATUS_READY, STATUS_FAILED}
DAYTONA_MCP_PORT_BASE = 20000
DAYTONA_MCP_PORT_SPAN = 20000
DAYTONA_MCP_PROXY_DIR = "/tmp/openwork-mcp"
DAYTONA_MCP_PROXY_PATH = "/mcp"
DAYTONA_MCP_PREVIEW_TTL_SECONDS = 3600
DAYTONA_MCP_READY_RETRIES = 20
DAYTONA_MCP_READY_INTERVAL_SECONDS = 0.5


def utcnow() -> dt.datetime:
    return dt.datetime.utcnow()


def normalize_mcp_key(key: str) -> str:
    normalized = (key or "").strip().lower()
    if not MCP_KEY_PATTERN.fullmatch(normalized):
        raise ValueError(
            "Invalid MCP key. Use lowercase letters, digits, hyphen, length 1-64."
        )
    return normalized


def normalize_transport(transport: str) -> str:
    normalized = (transport or "").strip().lower()
    if normalized not in MCP_TRANSPORTS:
        raise ValueError("Invalid MCP transport. Must be one of: streamable_http, sse, stdio.")
    return normalized


def _clean_str_map(value: Any, *, field: str) -> dict[str, str]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError(f"{field} must be an object of string key/value pairs.")
    cleaned: dict[str, str] = {}
    for k, v in value.items():
        key = str(k).strip()
        if not key:
            raise ValueError(f"{field} contains an empty key.")
        cleaned[key] = str(v)
    return cleaned


def normalize_mcp_payload(
    *,
    transport: str,
    config: dict[str, Any] | None,
    secret: dict[str, Any] | None,
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    transport = normalize_transport(transport)
    raw_config = config if isinstance(config, dict) else {}
    raw_secret = secret if isinstance(secret, dict) else {}

    if transport in {"streamable_http", "sse"}:
        url = str(raw_config.get("url", "")).strip()
        if not url:
            raise ValueError("HTTP/SSE MCP config requires 'url'.")
        safe_config: dict[str, Any] = {"url": url}
        headers = _clean_str_map(raw_secret.get("headers"), field="secret.headers")
        safe_secret = {"headers": headers} if headers else None
        return safe_config, safe_secret

    # stdio
    command = str(raw_config.get("command", "")).strip()
    if not command:
        raise ValueError("STDIO MCP config requires 'command'.")
    args_raw = raw_config.get("args") or []
    if not isinstance(args_raw, list):
        raise ValueError("STDIO MCP config 'args' must be a string array.")
    args = [str(item) for item in args_raw]
    safe_config = {"command": command, "args": args}
    env = _clean_str_map(raw_secret.get("env"), field="secret.env")
    safe_secret = {"env": env} if env else None
    return safe_config, safe_secret


def serialize_secret(secret: dict[str, Any] | None) -> str | None:
    if not secret:
        return None
    return encrypt(json.dumps(secret, ensure_ascii=False, separators=(",", ":")))


def deserialize_secret(token: str | None) -> dict[str, Any]:
    if not token:
        return {}
    try:
        raw = decrypt(token)
        value = json.loads(raw)
        if isinstance(value, dict):
            return value
    except Exception:
        pass
    return {}


def ensure_mcp_owned(db: Session, *, mcp_id: str, user_id: str) -> MCPServer:
    mcp = db.get(MCPServer, mcp_id)
    if not mcp or mcp.user_id != user_id:
        raise ValueError("MCP server not found")
    return mcp


def _thread_bindings_query(thread_id: str) -> Select[Any]:
    return (
        select(ThreadMCPBinding)
        .options(joinedload(ThreadMCPBinding.mcp_server))
        .where(ThreadMCPBinding.thread_id == thread_id, ThreadMCPBinding.enabled.is_(True))
        .order_by(ThreadMCPBinding.position.asc())
    )


def get_runtime_thread_mcp_servers(db: Session, *, thread_id: str) -> list[MCPServer]:
    bindings = db.execute(_thread_bindings_query(thread_id)).unique().scalars().all()
    result: list[MCPServer] = []
    for binding in bindings:
        if binding.mcp_server and binding.mcp_server.enabled:
            result.append(binding.mcp_server)
    return result


def _safe_slug(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9._-]", "-", value).strip("-") or "mcp"


def _derive_daytona_mcp_port(*, thread_id: str, server_key: str) -> int:
    seed = f"{thread_id}:{server_key}".encode("utf-8")
    digest = hashlib.sha256(seed).digest()
    offset = int.from_bytes(digest[:2], byteorder="big") % DAYTONA_MCP_PORT_SPAN
    return DAYTONA_MCP_PORT_BASE + offset


def _build_stdio_shell_command(
    *,
    command: str,
    args: list[str],
    env: dict[str, str],
) -> str:
    base = " ".join([shlex.quote(command), *[shlex.quote(arg) for arg in args]])
    if not env:
        return base
    env_parts = [f"{key}={shlex.quote(value)}" for key, value in sorted(env.items())]
    return f"env {' '.join(env_parts)} {base}"


def _ensure_daytona_mcp_gateway(
    *,
    sandbox: Any,
    thread_id: str,
    server_key: str,
    command: str,
    args: list[str],
    env: dict[str, str],
) -> int:
    port = _derive_daytona_mcp_port(thread_id=thread_id, server_key=server_key)
    process_name = f"{_safe_slug(thread_id)}-{_safe_slug(server_key)}"
    stdio_command = _build_stdio_shell_command(
        command=command,
        args=args,
        env=env,
    )
    gateway_parts = [
        "npx",
        "-y",
        "supergateway",
        "--stdio",
        stdio_command,
        "--outputTransport",
        "streamableHttp",
        "--streamableHttpPath",
        DAYTONA_MCP_PROXY_PATH,
        "--port",
        str(port),
    ]
    gateway_command = " ".join(shlex.quote(part) for part in gateway_parts)

    startup_script = f"""
set -euo pipefail
ROOT={shlex.quote(DAYTONA_MCP_PROXY_DIR)}
NAME={shlex.quote(process_name)}
PORT={port}
PID_FILE="$ROOT/$NAME.pid"
LOG_FILE="$ROOT/$NAME.log"
STDIO_CMD={shlex.quote(command)}
mkdir -p "$ROOT"

# Non-interactive shells in Daytona may miss nvm-managed Node paths.
export PATH="/usr/local/bin:/usr/bin:/bin:$PATH"
for node_bin in /usr/local/nvm/versions/node/*/bin; do
  if [ -d "$node_bin" ]; then
    PATH="$node_bin:$PATH"
  fi
done
export PATH

if ! command -v npx >/dev/null 2>&1; then
  echo "npx is required but not found in sandbox PATH: $PATH" >&2
  exit 1
fi

if ! command -v "$STDIO_CMD" >/dev/null 2>&1; then
  echo "MCP stdio command '$STDIO_CMD' not found in sandbox PATH: $PATH" >&2
  exit 1
fi

find_supergateway_pids_by_port() {{
  for proc in /proc/[0-9]*; do
    [ -r "$proc/cmdline" ] || continue
    cmdline="$(tr '\\000' ' ' < "$proc/cmdline" 2>/dev/null || true)"
    case "$cmdline" in
      *"supergateway"*"--port $PORT"*)
        echo "${{proc##*/}}"
        ;;
    esac
  done
}}

stop_if_running() {{
  pid="$1"
  [ -n "$pid" ] || return 0
  if ! is_pid_active "$pid"; then
    return 0
  fi
  kill "$pid" 2>/dev/null || true
  for _ in $(seq 1 20); do
    if ! is_pid_active "$pid"; then
      return 0
    fi
    sleep 0.1
  done
  kill -9 "$pid" 2>/dev/null || true
}}

is_pid_active() {{
  pid="$1"
  [ -n "$pid" ] || return 1
  [ -r "/proc/$pid/status" ] || return 1
  state="$(awk '/^State:/ {{ print $2 }}' "/proc/$pid/status" 2>/dev/null || true)"
  [ "$state" = "Z" ] && return 1
  kill -0 "$pid" 2>/dev/null
}}

OLD_PID=""
if [ -f "$PID_FILE" ]; then
  OLD_PID="$(cat "$PID_FILE" || true)"
fi
EXISTING_PIDS="$(find_supergateway_pids_by_port || true)"
if [ -n "$OLD_PID" ]; then
  EXISTING_PIDS="$OLD_PID $EXISTING_PIDS"
fi
for pid in $EXISTING_PIDS; do
  stop_if_running "$pid"
done
for pid in $EXISTING_PIDS; do
  if is_pid_active "$pid"; then
    echo "Failed to stop existing supergateway pid=$pid on port $PORT" >&2
    exit 1
  fi
done
rm -f "$PID_FILE"

nohup sh -c {shlex.quote(gateway_command)} >"$LOG_FILE" 2>&1 &
echo $! >"$PID_FILE"
sleep 1

PID="$(cat "$PID_FILE" || true)"
if [ -z "$PID" ] || ! kill -0 "$PID" 2>/dev/null; then
  echo "Failed to start gateway process. log=$LOG_FILE" >&2
  tail -n 120 "$LOG_FILE" >&2 || true
  exit 1
fi
"""
    result = sandbox.process.exec(startup_script, timeout=60)
    exit_code = getattr(result, "exit_code", 1)
    output = str(getattr(result, "result", "") or "")
    if exit_code != 0:
        raise RuntimeError(
            f"Failed to start MCP proxy in Daytona for '{server_key}'. "
            f"exit_code={exit_code} output={output}"
        )
    return port


def _wait_for_daytona_bridge_ready(url: str) -> None:
    last_error: Exception | None = None
    for _ in range(DAYTONA_MCP_READY_RETRIES):
        try:
            response = httpx.get(
                url,
                timeout=2.0,
                follow_redirects=True,
                trust_env=False,
            )
            if response.status_code < 500:
                return
        except Exception as e:
            last_error = e
        time.sleep(DAYTONA_MCP_READY_INTERVAL_SECONDS)
    if last_error is not None:
        raise RuntimeError(f"MCP proxy at '{url}' is not reachable: {last_error}") from last_error
    raise RuntimeError(f"MCP proxy at '{url}' is not reachable")


def _create_daytona_httpx_client(
    headers: dict[str, str] | None = None,
    timeout: httpx.Timeout | None = None,
    auth: httpx.Auth | None = None,
) -> httpx.AsyncClient:
    # Preview URLs are internal Daytona endpoints and should bypass host proxy env vars.
    return httpx.AsyncClient(
        headers=headers,
        timeout=timeout,
        auth=auth,
        trust_env=False,
    )


def _build_daytona_mcp_client_entry(
    *,
    server_key: str,
    thread_id: str,
    daytona_sandbox: Any,
    command: str,
    args: list[str],
    env: dict[str, str],
) -> dict[str, Any]:
    port = _ensure_daytona_mcp_gateway(
        sandbox=daytona_sandbox,
        thread_id=thread_id,
        server_key=server_key,
        command=command,
        args=args,
        env=env,
    )
    preview = daytona_sandbox.create_signed_preview_url(
        port,
        expires_in_seconds=DAYTONA_MCP_PREVIEW_TTL_SECONDS,
    )
    base_url = str(getattr(preview, "url", "") or "").rstrip("/")
    if not base_url:
        raise RuntimeError(f"Failed to resolve Daytona preview URL for MCP '{server_key}'")
    mcp_url = f"{base_url}{DAYTONA_MCP_PROXY_PATH}"
    _wait_for_daytona_bridge_ready(mcp_url)
    return {
        "transport": "streamable_http",
        "url": mcp_url,
        "httpx_client_factory": _create_daytona_httpx_client,
    }


def build_mcp_client_entry(
    server: MCPServer,
    *,
    thread_id: str | None = None,
    daytona_sandbox: Any | None = None,
) -> dict[str, Any]:
    config = server.config_json if isinstance(server.config_json, dict) else {}
    secret = deserialize_secret(server.encrypted_secret_json)
    transport = normalize_transport(server.transport)

    if transport in {"streamable_http", "sse"}:
        url = str(config.get("url", "")).strip()
        if not url:
            raise ValueError(f"MCP '{server.key}' missing config.url")
        entry: dict[str, Any] = {"transport": transport, "url": url}
        headers = _clean_str_map(secret.get("headers"), field="secret.headers")
        if headers:
            entry["headers"] = headers
        return entry

    command = str(config.get("command", "")).strip()
    if not command:
        raise ValueError(f"MCP '{server.key}' missing config.command")
    args = config.get("args") or []
    if not isinstance(args, list):
        raise ValueError(f"MCP '{server.key}' has invalid config.args")
    args_str = [str(v) for v in args]
    env = _clean_str_map(secret.get("env"), field="secret.env")
    if daytona_sandbox is not None:
        if not thread_id:
            raise ValueError("thread_id is required when building MCP entries for Daytona sandbox")
        return _build_daytona_mcp_client_entry(
            server_key=server.key,
            thread_id=thread_id,
            daytona_sandbox=daytona_sandbox,
            command=command,
            args=args_str,
            env=env,
        )

    entry = {"transport": "stdio", "command": command, "args": args_str}
    if env:
        entry["env"] = env
    return entry


def build_thread_mcp_client_configs(
    db: Session,
    *,
    thread_id: str,
    daytona_sandbox: Any | None = None,
) -> dict[str, dict[str, Any]]:
    servers = get_runtime_thread_mcp_servers(db, thread_id=thread_id)
    configs: dict[str, dict[str, Any]] = {}
    for server in servers:
        configs[server.key] = build_mcp_client_entry(
            server,
            thread_id=thread_id,
            daytona_sandbox=daytona_sandbox,
        )
    return configs


def update_thread_mcp_runtime_state(
    db: Session,
    *,
    thread_id: str,
    status: str,
    last_error: str | None = None,
) -> ThreadMCPRuntimeState:
    if status not in VALID_STATUSES:
        raise ValueError(f"Invalid MCP runtime status: {status}")

    state = db.get(ThreadMCPRuntimeState, thread_id)
    if not state:
        state = ThreadMCPRuntimeState(
            thread_id=thread_id,
            status=status,
            last_error=last_error,
            updated_at=utcnow(),
        )
        db.add(state)
    else:
        state.status = status
        state.last_error = last_error
        state.updated_at = utcnow()
    return state


def refresh_thread_mcp_runtime_state(db: Session, *, thread_id: str) -> ThreadMCPRuntimeState:
    has_enabled_mcp = (
        db.execute(
            select(ThreadMCPBinding.id)
            .join(MCPServer, ThreadMCPBinding.mcp_id == MCPServer.id)
            .where(
                ThreadMCPBinding.thread_id == thread_id,
                ThreadMCPBinding.enabled.is_(True),
                MCPServer.enabled.is_(True),
            )
            .limit(1)
        )
        .scalars()
        .first()
    )
    if has_enabled_mcp:
        return update_thread_mcp_runtime_state(
            db,
            thread_id=thread_id,
            status=STATUS_DIRTY,
            last_error=None,
        )
    return update_thread_mcp_runtime_state(
        db,
        thread_id=thread_id,
        status=STATUS_READY,
        last_error=None,
    )


def _resolve_user_thread_ids(
    db: Session,
    *,
    user_id: str,
    thread_ids: list[str] | None = None,
) -> list[str]:
    if thread_ids is None:
        return (
            db.execute(
                select(Thread.id)
                .where(Thread.user_id == user_id)
                .order_by(Thread.created_at.asc(), Thread.id.asc())
            )
            .scalars()
            .all()
        )

    normalized_ids = sorted({str(thread_id) for thread_id in thread_ids if thread_id})
    if not normalized_ids:
        return []

    owned_ids = (
        db.execute(
            select(Thread.id).where(
                Thread.user_id == user_id,
                Thread.id.in_(normalized_ids),
            )
        )
        .scalars()
        .all()
    )
    if len(owned_ids) != len(normalized_ids):
        raise ValueError("One or more threads are invalid")
    return sorted(owned_ids)


def _enabled_user_mcp_ids(db: Session, *, user_id: str) -> list[str]:
    return (
        db.execute(
            select(MCPServer.id)
            .where(MCPServer.user_id == user_id, MCPServer.enabled.is_(True))
            .order_by(MCPServer.created_at.asc(), MCPServer.id.asc())
        )
        .scalars()
        .all()
    )


def sync_user_mcp_bindings(
    db: Session,
    *,
    user_id: str,
    thread_ids: list[str] | None = None,
) -> list[str]:
    # SessionLocal is configured with autoflush=False.
    db.flush()
    target_thread_ids = _resolve_user_thread_ids(db, user_id=user_id, thread_ids=thread_ids)
    if not target_thread_ids:
        return []

    enabled_mcp_ids = _enabled_user_mcp_ids(db, user_id=user_id)
    db.query(ThreadMCPBinding).filter(ThreadMCPBinding.thread_id.in_(target_thread_ids)).delete(
        synchronize_session=False
    )

    now = utcnow()
    for thread_id in target_thread_ids:
        for position, mcp_id in enumerate(enabled_mcp_ids):
            db.add(
                ThreadMCPBinding(
                    thread_id=thread_id,
                    mcp_id=mcp_id,
                    position=position,
                    enabled=True,
                    created_at=now,
                    updated_at=now,
                )
            )

    # SessionLocal is configured with autoflush=False.
    db.flush()
    for thread_id in target_thread_ids:
        refresh_thread_mcp_runtime_state(db, thread_id=thread_id)
    return target_thread_ids


def refresh_runtime_state_for_mcp(db: Session, *, mcp_id: str) -> None:
    thread_ids = list_thread_ids_for_mcp(db, mcp_id=mcp_id)
    for thread_id in sorted(set(thread_ids)):
        refresh_thread_mcp_runtime_state(db, thread_id=thread_id)


def list_thread_ids_for_mcp(db: Session, *, mcp_id: str) -> list[str]:
    return (
        db.execute(
            select(ThreadMCPBinding.thread_id).where(
                ThreadMCPBinding.mcp_id == mcp_id,
                ThreadMCPBinding.enabled.is_(True),
            )
        )
        .scalars()
        .all()
    )
