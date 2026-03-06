from __future__ import annotations

import logging
import platform
import shutil
from pathlib import Path

from ..config import SandboxConfig
from .local_sandbox import LocalSandbox
from .nsjail_sandbox import NsjailSandbox
from .types import ExecuteResult, SandboxRunner

logger = logging.getLogger(__name__)


def build_sandbox(workspace_root: str, config: SandboxConfig) -> SandboxRunner:
    if not config.enabled:
        raise RuntimeError("Sandbox is required but disabled in config")

    current_platform = platform.system()
    if current_platform == "Linux":
        nsjail_path = shutil.which(config.nsjail_path) or config.nsjail_path
        if Path(nsjail_path).exists():
            return NsjailSandbox(workspace_root, config)
        reason = f"nsjail not found at '{config.nsjail_path}'"
    else:
        reason = f"platform '{current_platform}' is not Linux"

    logger.warning(
        "Falling back to LocalSandbox for workspace '%s': %s",
        workspace_root,
        reason,
    )
    return LocalSandbox(workspace_root, config)


__all__ = [
    "ExecuteResult",
    "SandboxRunner",
    "NsjailSandbox",
    "LocalSandbox",
    "build_sandbox",
]
