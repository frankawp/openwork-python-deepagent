from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class DatabaseConfig:
    url: str


@dataclass(frozen=True)
class AuthConfig:
    jwt_secret: str
    access_ttl_min: int
    refresh_ttl_days: int


@dataclass(frozen=True)
class WorkspaceConfig:
    root: str


@dataclass(frozen=True)
class DataConfig:
    dir: str


@dataclass(frozen=True)
class AdminConfig:
    email: str
    password: str


@dataclass(frozen=True)
class AppConfig:
    database: DatabaseConfig
    auth: AuthConfig
    workspace: WorkspaceConfig
    data: DataConfig
    admin: AdminConfig


_CONFIG: AppConfig | None = None


def _require_key(data: dict[str, Any], key: str) -> Any:
    if key not in data:
        raise ValueError(f"Missing config key: {key}")
    return data[key]


def load_config(path: str | None = None) -> AppConfig:
    global _CONFIG
    if _CONFIG is not None:
        return _CONFIG

    config_path = Path(path or "config.yaml").resolve()
    if not config_path.exists():
        raise FileNotFoundError(
            f"Config file not found: {config_path}. Copy config.example.yaml to config.yaml."
        )

    with config_path.open("r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}

    db_raw = _require_key(raw, "database")
    auth_raw = _require_key(raw, "auth")
    workspace_raw = _require_key(raw, "workspace")
    data_raw = _require_key(raw, "data")
    admin_raw = _require_key(raw, "admin")

    _CONFIG = AppConfig(
        database=DatabaseConfig(url=_require_key(db_raw, "url")),
        auth=AuthConfig(
            jwt_secret=_require_key(auth_raw, "jwt_secret"),
            access_ttl_min=int(_require_key(auth_raw, "access_ttl_min")),
            refresh_ttl_days=int(_require_key(auth_raw, "refresh_ttl_days")),
        ),
        workspace=WorkspaceConfig(root=_require_key(workspace_raw, "root")),
        data=DataConfig(dir=_require_key(data_raw, "dir")),
        admin=AdminConfig(
            email=_require_key(admin_raw, "email"),
            password=_require_key(admin_raw, "password"),
        ),
    )
    return _CONFIG
