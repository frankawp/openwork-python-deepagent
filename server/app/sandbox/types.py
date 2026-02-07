from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class ExecuteResult:
    output: str
    exit_code: int | None
    truncated: bool


class SandboxRunner(Protocol):
    def run(
        self,
        command: str,
        *,
        env: dict[str, str] | None = None,
        timeout_seconds: int | None = None,
        max_output_bytes: int | None = None,
    ) -> ExecuteResult:
        ...
