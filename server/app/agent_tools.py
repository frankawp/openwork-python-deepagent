from __future__ import annotations

import subprocess
from typing import Callable

from langchain_core.tools import tool


def make_execute_tool(workspace_path: str, timeout_seconds: int = 120, max_output_bytes: int = 100_000):
    @tool("execute")
    def execute(command: str) -> str:
        """Run a shell command in the workspace directory and return output."""
        if not command or not isinstance(command, str):
            return "Error: Shell tool expects a non-empty command string."

        try:
            proc = subprocess.run(
                command,
                shell=True,
                cwd=workspace_path,
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
