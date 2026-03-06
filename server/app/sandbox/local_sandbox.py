from __future__ import annotations

import os
import subprocess
from pathlib import Path

from ..config import SandboxConfig
from .types import ExecuteResult


class LocalSandbox:
    def __init__(self, workspace_root: str, config: SandboxConfig) -> None:
        self.workspace_root = Path(workspace_root)
        self.config = config
        self.workspace_root.mkdir(parents=True, exist_ok=True)

    def run(
        self,
        command: str,
        *,
        env: dict[str, str] | None = None,
        timeout_seconds: int | None = None,
        max_output_bytes: int | None = None,
    ) -> ExecuteResult:
        if not command or not isinstance(command, str):
            return ExecuteResult(
                output="Error: Shell tool expects a non-empty command string.",
                exit_code=1,
                truncated=False,
            )

        timeout = timeout_seconds or self.config.time_limit_sec
        output_limit = max_output_bytes or self.config.max_output_bytes

        base_env = dict(env or {})
        if "HOME" not in base_env:
            base_env["HOME"] = str(self.workspace_root)
        if "LANG" not in base_env:
            base_env["LANG"] = "C.UTF-8"
        if "PATH" not in base_env:
            base_env["PATH"] = os.environ.get("PATH", "")

        try:
            proc = subprocess.run(
                ["/bin/sh", "-c", command],
                cwd=str(self.workspace_root),
                env=base_env,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired:
            return ExecuteResult(
                output=f"Error: Command timed out after {timeout} seconds.",
                exit_code=None,
                truncated=False,
            )
        except Exception as exc:  # pragma: no cover - defensive
            return ExecuteResult(
                output=f"Error: Failed to run command. {exc}",
                exit_code=1,
                truncated=False,
            )

        output = ""
        if proc.stdout:
            output += proc.stdout
        if proc.stderr:
            for line in proc.stderr.splitlines():
                output += f"[stderr] {line}\n"

        if not output.strip():
            output = "<no output>"

        truncated = False
        if len(output) > output_limit:
            output = output[:output_limit] + "\n\n... Output truncated."
            truncated = True

        return ExecuteResult(
            output=output,
            exit_code=proc.returncode,
            truncated=truncated,
        )
