from __future__ import annotations

import os
import shlex
import subprocess
from pathlib import Path
from typing import Callable

from langchain_core.tools import tool


def _is_within_root(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _map_virtual_path(path_str: str, workspace_root: Path) -> str:
    if any(ch in path_str for ch in ("*", "?", "[")):
        return path_str
    if path_str.startswith("~"):
        return path_str
    if ".." in Path(path_str).parts:
        return path_str

    candidate = (workspace_root / path_str.lstrip("/")).resolve()
    if not _is_within_root(candidate, workspace_root):
        return path_str

    # If the system path exists, keep it as-is.
    if Path(path_str).exists():
        return path_str

    # Otherwise treat it as a workspace-virtual path.
    return str(candidate)


def _rewrite_virtual_paths_in_command(command: str, workspace_root: str) -> str:
    try:
        tokens = shlex.split(command)
    except ValueError:
        return command
    if not tokens:
        return command

    root = Path(workspace_root).resolve()
    rewritten: list[str] = []
    for token in tokens:
        if token.startswith("/"):
            rewritten.append(_map_virtual_path(token, root))
            continue
        if "=" in token:
            left, right = token.split("=", 1)
            if right.startswith("/") and ":" not in right:
                mapped = _map_virtual_path(right, root)
                rewritten.append(f"{left}={mapped}")
                continue
        rewritten.append(token)
    try:
        return shlex.join(rewritten)
    except AttributeError:
        return " ".join(shlex.quote(token) for token in rewritten)


def make_execute_tool(workspace_path: str, timeout_seconds: int = 120, max_output_bytes: int = 100_000):
    @tool("execute")
    def execute(command: str) -> str:
        """Run a shell command in the workspace directory and return output."""
        if not command or not isinstance(command, str):
            return "Error: Shell tool expects a non-empty command string."

        command = _rewrite_virtual_paths_in_command(command, workspace_path)

        try:
            proc = subprocess.run(
                command,
                shell=True,
                cwd=workspace_path,
                env={**os.environ, "WORKSPACE_ROOT": workspace_path},
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
            )
        except subprocess.TimeoutExpired:
            return f"Error: Command timed out after {timeout_seconds} seconds."
        except Exception as e:
            return f"Error: Failed to run command. {e}"

        output = ""
        if proc.stdout:
            output += proc.stdout
        if proc.stderr:
            for line in proc.stderr.splitlines():
                output += f"[stderr] {line}\n"

        if not output.strip():
            output = "<no output>"

        if len(output) > max_output_bytes:
            output = output[:max_output_bytes] + "\n\n... Output truncated."

        return output

    return execute
