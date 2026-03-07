from __future__ import annotations

import shlex
from dataclasses import dataclass
from typing import Any

from .analysis_env import DEFAULT_REQUIREMENTS
from .db import SessionLocal
from .models import Thread

_DAYTONA_THREAD_KEY = "daytona"
_DAYTONA_SANDBOX_ID_KEY = "sandbox_id"
_DAYTONA_WORKSPACE_ROOT_KEY = "workspace_root"
_DAYTONA_DEFAULT_WORKSPACE_ROOT = "/home/daytona"


@dataclass(frozen=True)
class DaytonaBackendContext:
    backend: Any
    workspace_root: str


def ensure_daytona_configured() -> None:
    _create_daytona_client()


def get_or_create_daytona_backend(
    *,
    thread_id: str,
    command_timeout_seconds: int,
) -> DaytonaBackendContext:
    try:
        from daytona import CreateSandboxFromSnapshotParams
        from langchain_daytona import DaytonaSandbox
    except Exception as e:  # pragma: no cover - import guard
        raise RuntimeError(
            "langchain-daytona/daytona are required for Daytona backend. "
            "Install dependencies in the server venv."
        ) from e

    daytona = _create_daytona_client()

    sandbox_id = _get_thread_daytona_sandbox_id(thread_id)
    sandbox = None
    if sandbox_id:
        try:
            sandbox = daytona.get(sandbox_id)
        except Exception:
            sandbox = None

    if sandbox is None:
        params = CreateSandboxFromSnapshotParams(
            language="python",
            labels={
                "openwork_app": "openwork",
                "openwork_thread_id": thread_id,
            },
        )
        sandbox = daytona.create(params=params, timeout=120)
        _set_thread_daytona_sandbox_id(thread_id, sandbox.id)

    workspace_root = _resolve_workspace_root(sandbox)
    _set_thread_daytona_workspace_root(thread_id, workspace_root)

    backend = DaytonaSandbox(sandbox=sandbox)
    # langchain-daytona currently uses a 30-minute default timeout.
    # Align it with server sandbox timeout to keep behavior predictable.
    if hasattr(backend, "_default_timeout"):
        backend._default_timeout = int(command_timeout_seconds)  # type: ignore[attr-defined]

    return DaytonaBackendContext(backend=backend, workspace_root=workspace_root)


def ensure_daytona_thread_environment(
    *,
    thread_id: str,
    command_timeout_seconds: int,
) -> str:
    context = get_or_create_daytona_backend(
        thread_id=thread_id,
        command_timeout_seconds=command_timeout_seconds,
    )
    _ensure_analysis_layout_in_daytona(
        context.backend,
        workspace_root=context.workspace_root,
        command_timeout_seconds=command_timeout_seconds,
    )
    return context.workspace_root


def delete_daytona_sandbox_for_thread(thread_id: str) -> None:
    sandbox_id = _get_thread_daytona_sandbox_id(thread_id)
    if not sandbox_id:
        return

    daytona = _create_daytona_client()
    try:
        sandbox = daytona.get(sandbox_id)
        daytona.delete(sandbox, timeout=120)
    except Exception:
        # Ignore cleanup failures to avoid blocking thread deletion.
        pass


def _create_daytona_client():
    try:
        from daytona import Daytona
    except Exception as e:  # pragma: no cover - import guard
        raise RuntimeError(
            "daytona SDK is not installed. Install server dependencies first."
        ) from e

    try:
        return Daytona()
    except Exception as e:
        raise RuntimeError(
            "Daytona is not configured. Set DAYTONA_API_KEY (and optionally DAYTONA_API_URL / DAYTONA_TARGET)."
        ) from e


def _resolve_workspace_root(sandbox: Any) -> str:
    try:
        work_dir = sandbox.get_work_dir()
    except Exception:
        return _DAYTONA_DEFAULT_WORKSPACE_ROOT

    if isinstance(work_dir, str) and work_dir.startswith("/"):
        stripped = work_dir.rstrip("/")
        return stripped or "/"
    return _DAYTONA_DEFAULT_WORKSPACE_ROOT


def _ensure_analysis_layout_in_daytona(
    backend: Any,
    *,
    workspace_root: str,
    command_timeout_seconds: int,
) -> None:
    requirements = DEFAULT_REQUIREMENTS.rstrip("\n")
    analysis_dir = f"{workspace_root.rstrip('/')}/analysis"
    requirements_path = f"{analysis_dir}/requirements.txt"
    escaped_inputs = shlex.quote(f"{analysis_dir}/inputs")
    escaped_scripts = shlex.quote(f"{analysis_dir}/scripts")
    escaped_figures = shlex.quote(f"{analysis_dir}/figures")
    escaped_outputs = shlex.quote(f"{analysis_dir}/outputs")
    escaped_requirements = shlex.quote(requirements_path)
    command = (
        f"mkdir -p {escaped_inputs} {escaped_scripts} {escaped_figures} {escaped_outputs} && "
        f"if [ ! -f {escaped_requirements} ]; then "
        f"cat > {escaped_requirements} <<'EOF'\n{requirements}\nEOF\n"
        "fi"
    )

    timeout = max(int(command_timeout_seconds), 10)
    result = backend.execute(command, timeout=timeout)
    if result.exit_code != 0:
        message = result.output or "unknown error"
        raise RuntimeError(f"Failed to prepare Daytona analysis workspace: {message}")


def _get_thread_daytona_sandbox_id(thread_id: str) -> str | None:
    db = SessionLocal()
    try:
        thread = db.get(Thread, thread_id)
        if not thread:
            return None
        values = thread.thread_values or {}
        if not isinstance(values, dict):
            return None
        daytona_values = values.get(_DAYTONA_THREAD_KEY)
        if not isinstance(daytona_values, dict):
            return None
        sandbox_id = daytona_values.get(_DAYTONA_SANDBOX_ID_KEY)
        if isinstance(sandbox_id, str) and sandbox_id:
            return sandbox_id
        return None
    finally:
        db.close()


def _set_thread_daytona_workspace_root(thread_id: str, workspace_root: str) -> None:
    db = SessionLocal()
    try:
        thread = db.get(Thread, thread_id)
        if not thread:
            return
        current_values = thread.thread_values
        values: dict[str, Any] = dict(current_values) if isinstance(current_values, dict) else {}
        raw_daytona_values = values.get(_DAYTONA_THREAD_KEY)
        daytona_values = (
            dict(raw_daytona_values) if isinstance(raw_daytona_values, dict) else {}
        )
        daytona_values[_DAYTONA_WORKSPACE_ROOT_KEY] = workspace_root
        values[_DAYTONA_THREAD_KEY] = daytona_values
        thread.thread_values = values
        db.commit()
    finally:
        db.close()


def _set_thread_daytona_sandbox_id(thread_id: str, sandbox_id: str) -> None:
    db = SessionLocal()
    try:
        thread = db.get(Thread, thread_id)
        if not thread:
            return
        current_values = thread.thread_values
        values: dict[str, Any] = dict(current_values) if isinstance(current_values, dict) else {}
        raw_daytona_values = values.get(_DAYTONA_THREAD_KEY)
        daytona_values = (
            dict(raw_daytona_values) if isinstance(raw_daytona_values, dict) else {}
        )
        daytona_values[_DAYTONA_SANDBOX_ID_KEY] = sandbox_id
        values[_DAYTONA_THREAD_KEY] = daytona_values
        thread.thread_values = values
        db.commit()
    finally:
        db.close()
