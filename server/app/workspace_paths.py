from __future__ import annotations

from pathlib import Path

from .config import load_config


def workspace_root_path() -> Path:
    return Path(load_config().workspace.root).resolve()


def user_workspace_path(username: str, *, create: bool = False) -> Path:
    root = workspace_root_path()
    workspace = (root / username).resolve()
    try:
        workspace.relative_to(root)
    except ValueError as e:
        raise ValueError("Invalid workspace path") from e

    if create:
        workspace.mkdir(parents=True, exist_ok=True)
    return workspace
