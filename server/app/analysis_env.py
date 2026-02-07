from __future__ import annotations

import os
from pathlib import Path

from .sandbox.types import ExecuteResult, SandboxRunner

DEFAULT_REQUIREMENTS = """pandas
numpy
matplotlib
seaborn
scipy
statsmodels
"""


def build_base_env(workspace_root: str) -> dict[str, str]:
    return {
        "WORKSPACE_ROOT": workspace_root,
        "PATH": os.environ.get("PATH", ""),
        "HOME": os.environ.get("HOME", "/tmp"),
        "LANG": os.environ.get("LANG", "C.UTF-8"),
    }


def build_execution_env(workspace_root: str) -> dict[str, str]:
    env = build_base_env(workspace_root)
    venv_path = Path(workspace_root) / ".venv"
    if venv_path.exists():
        env["VIRTUAL_ENV"] = str(venv_path)
        env["PATH"] = f"{venv_path / 'bin'}:{env.get('PATH', '')}"
    return env


def _ensure_directories(root: Path) -> None:
    (root / "analysis" / "inputs").mkdir(parents=True, exist_ok=True)
    (root / "analysis" / "scripts").mkdir(parents=True, exist_ok=True)
    (root / "analysis" / "figures").mkdir(parents=True, exist_ok=True)
    (root / "analysis" / "outputs").mkdir(parents=True, exist_ok=True)


def _write_requirements(requirements_path: Path) -> None:
    if not requirements_path.exists():
        requirements_path.write_text(DEFAULT_REQUIREMENTS, encoding="utf-8")


def _run_or_raise(
    sandbox: SandboxRunner,
    command: str,
    env: dict[str, str],
    timeout_seconds: int | None,
    max_output_bytes: int | None,
) -> ExecuteResult:
    result = sandbox.run(
        command,
        env=env,
        timeout_seconds=timeout_seconds,
        max_output_bytes=max_output_bytes,
    )
    if result.exit_code != 0:
        raise RuntimeError(result.output)
    return result


def ensure_analysis_environment(
    workspace_root: str,
    sandbox: SandboxRunner,
    *,
    timeout_seconds: int | None = None,
    max_output_bytes: int | None = None,
) -> None:
    root = Path(workspace_root)
    _ensure_directories(root)

    requirements_path = root / "analysis" / "requirements.txt"
    _write_requirements(requirements_path)

    venv_path = root / ".venv"
    if not venv_path.exists():
        base_env = build_base_env(workspace_root)
        _run_or_raise(
            sandbox,
            "uv venv .venv",
            base_env,
            timeout_seconds,
            max_output_bytes,
        )
        venv_path.mkdir(exist_ok=True)

        venv_env = build_execution_env(workspace_root)
        _run_or_raise(
            sandbox,
            ".venv/bin/uv pip install -r analysis/requirements.txt",
            venv_env,
            timeout_seconds,
            max_output_bytes,
        )
