from __future__ import annotations

import logging
import shlex
from dataclasses import dataclass
from typing import Any

from .analysis_env import ANALYSIS_DIR_NAME, ANALYSIS_SUBDIRS, DEFAULT_REQUIREMENTS
from .config import load_config
from .db import SessionLocal
from .models import Thread

_DAYTONA_THREAD_KEY = "daytona"
_DAYTONA_SANDBOX_ID_KEY = "sandbox_id"
_DAYTONA_WORKSPACE_ROOT_KEY = "workspace_root"
_DAYTONA_DEFAULT_WORKSPACE_ROOT = "/home/daytona"
logger = logging.getLogger(__name__)


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
    allow_create_if_missing: bool = False,
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

    if not sandbox_id:
        if not allow_create_if_missing:
            raise RuntimeError(
                "Daytona sandbox is not initialized for this thread. "
                "Please create a new session to provision a sandbox."
            )
        sandbox = _create_daytona_sandbox(
            daytona=daytona,
            create_params_cls=CreateSandboxFromSnapshotParams,
            thread_id=thread_id,
        )
        _set_thread_daytona_sandbox_id(thread_id, sandbox.id)
    else:
        try:
            sandbox = daytona.get(sandbox_id)
        except Exception as e:
            raise RuntimeError(
                f"Daytona sandbox not found or inaccessible (sandbox_id={sandbox_id}). "
                "Automatic recreation is disabled. Please create a new session."
            ) from e

    workspace_root = _resolve_workspace_root(sandbox)
    _set_thread_daytona_workspace_root(thread_id, workspace_root)

    backend = _create_daytona_backend(
        DaytonaSandbox,
        sandbox=sandbox,
        command_timeout_seconds=command_timeout_seconds,
    )
    _assert_backend_available(
        backend=backend,
        command_timeout_seconds=command_timeout_seconds,
        sandbox_id=getattr(sandbox, "id", None),
    )

    return DaytonaBackendContext(backend=backend, workspace_root=workspace_root)


def ensure_daytona_thread_environment(
    *,
    thread_id: str,
    command_timeout_seconds: int,
) -> str:
    context = get_or_create_daytona_backend(
        thread_id=thread_id,
        command_timeout_seconds=command_timeout_seconds,
        allow_create_if_missing=True,
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
        logger.exception(
            "Failed to delete Daytona sandbox during thread deletion "
            "(thread_id=%s sandbox_id=%s)",
            thread_id,
            sandbox_id,
        )


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


def _create_daytona_sandbox(*, daytona: Any, create_params_cls: Any, thread_id: str) -> Any:
    cfg = load_config()
    base_kwargs = {
        "language": "python",
        "labels": {
            "openwork_app": "openwork",
            "openwork_thread_id": thread_id,
        },
    }
    lifecycle_kwargs = {
        "auto_stop_interval": cfg.sandbox.daytona_auto_stop_interval_min,
        "auto_archive_interval": cfg.sandbox.daytona_auto_archive_interval_days,
        "auto_delete_interval": cfg.sandbox.daytona_auto_delete_interval_days,
    }
    try:
        params = create_params_cls(**base_kwargs, **lifecycle_kwargs)
    except TypeError:
        # Backward compatibility for SDK versions without lifecycle args.
        params = create_params_cls(**base_kwargs)
    return daytona.create(params=params, timeout=120)


def _create_daytona_backend(
    backend_cls: Any,
    *,
    sandbox: Any,
    command_timeout_seconds: int,
) -> Any:
    backend = backend_cls(sandbox=sandbox)
    # langchain-daytona currently uses a 30-minute default timeout.
    # Align it with server sandbox timeout to keep behavior predictable.
    if hasattr(backend, "_default_timeout"):
        backend._default_timeout = int(command_timeout_seconds)  # type: ignore[attr-defined]
    return backend


def _assert_backend_available(
    *,
    backend: Any,
    command_timeout_seconds: int,
    sandbox_id: str | None,
) -> None:
    timeout = max(5, min(int(command_timeout_seconds), 20))
    try:
        result = backend.execute("pwd", timeout=timeout)
    except Exception as e:
        sid = f" sandbox_id={sandbox_id}" if sandbox_id else ""
        raise RuntimeError(
            f"Failed to execute command: backend unavailable{sid}. {e}"
        ) from e

    exit_code = getattr(result, "exit_code", 1)
    if exit_code == 0:
        return

    output = str(getattr(result, "output", "") or "").lower()
    sid = f" sandbox_id={sandbox_id}" if sandbox_id else ""
    if "no ip address found" in output:
        raise RuntimeError(
            f"Failed to execute command: bad request: no IP address found. "
            f"Is the Sandbox started?{sid}"
        )
    raise RuntimeError(
        f"Failed to execute command: backend unavailable{sid}. "
        f"exit_code={exit_code} output={getattr(result, 'output', '')}"
    )


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
    analysis_dir = f"{workspace_root.rstrip('/')}/{ANALYSIS_DIR_NAME}"
    requirements_path = f"{analysis_dir}/requirements.txt"
    escaped_subdirs = [shlex.quote(f"{analysis_dir}/{name}") for name in ANALYSIS_SUBDIRS]
    escaped_requirements = shlex.quote(requirements_path)
    command = (
        f"mkdir -p {' '.join(escaped_subdirs)} && "
        f"if [ ! -f {escaped_requirements} ]; then "
        f"cat > {escaped_requirements} <<'EOF'\n{requirements}\nEOF\n"
        "fi"
    )

    timeout = max(int(command_timeout_seconds), 10)
    result = backend.execute(command, timeout=timeout)
    if result.exit_code != 0:
        message = result.output or "unknown error"
        raise RuntimeError(f"Failed to prepare Daytona {ANALYSIS_DIR_NAME} workspace: {message}")


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
