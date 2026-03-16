from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


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
class SandboxConfig:
    enabled: bool
    time_limit_sec: int
    max_output_bytes: int
    daytona_auto_stop_interval_min: int
    daytona_auto_archive_interval_days: int
    daytona_auto_delete_interval_days: int


@dataclass(frozen=True)
class DaytonaConfig:
    api_key: str
    api_url: str | None
    target: str | None
    snapshot: str | None


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
    sandbox: SandboxConfig
    daytona: DaytonaConfig
    admin: AdminConfig


_CONFIG: AppConfig | None = None
_ENV_LOADED = False
_SERVER_ROOT = Path(__file__).resolve().parents[1]


def _strip_optional_quotes(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        return value[1:-1]
    return value


def _load_env_file(path: str | None = None) -> None:
    global _ENV_LOADED
    if _ENV_LOADED:
        return

    env_path = Path(path).resolve() if path else _SERVER_ROOT / ".env"
    if env_path.exists():
        for raw_line in env_path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("export "):
                line = line[7:].strip()
            if "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            if not key:
                continue
            os.environ.setdefault(key, _strip_optional_quotes(value.strip()))

    _ENV_LOADED = True


def _require_env(name: str) -> str:
    value = (os.environ.get(name) or "").strip()
    if not value:
        raise ValueError(
            f"Missing required environment variable: {name}. "
            "Copy server/.env.example to server/.env and fill the values."
        )
    return value


def _optional_env(name: str) -> str | None:
    value = (os.environ.get(name) or "").strip()
    return value or None


def _int_env(name: str, default: int) -> int:
    value = _optional_env(name)
    return int(value) if value is not None else default


def _bool_env(name: str, default: bool) -> bool:
    value = _optional_env(name)
    if value is None:
        return default
    normalized = value.lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"Invalid boolean environment variable: {name}={value}")


def load_config(path: str | None = None) -> AppConfig:
    global _CONFIG
    if _CONFIG is not None:
        return _CONFIG

    _load_env_file(path)

    _CONFIG = AppConfig(
        database=DatabaseConfig(url=_require_env("DATABASE_URL")),
        auth=AuthConfig(
            jwt_secret=_require_env("JWT_SECRET"),
            access_ttl_min=_int_env("ACCESS_TTL_MIN", 60),
            refresh_ttl_days=_int_env("REFRESH_TTL_DAYS", 7),
        ),
        workspace=WorkspaceConfig(root=_require_env("WORKSPACE_ROOT")),
        data=DataConfig(dir=_require_env("DATA_DIR")),
        sandbox=SandboxConfig(
            enabled=_bool_env("SANDBOX_ENABLED", True),
            time_limit_sec=_int_env("SANDBOX_TIME_LIMIT_SEC", 120),
            max_output_bytes=_int_env("SANDBOX_MAX_OUTPUT_BYTES", 100_000),
            daytona_auto_stop_interval_min=_int_env("DAYTONA_AUTO_STOP_INTERVAL_MIN", 0),
            daytona_auto_archive_interval_days=_int_env("DAYTONA_AUTO_ARCHIVE_INTERVAL_DAYS", 0),
            daytona_auto_delete_interval_days=_int_env("DAYTONA_AUTO_DELETE_INTERVAL_DAYS", -1),
        ),
        daytona=DaytonaConfig(
            api_key=_require_env("DAYTONA_API_KEY"),
            api_url=_optional_env("DAYTONA_API_URL"),
            target=_optional_env("DAYTONA_TARGET"),
            snapshot=_optional_env("DAYTONA_SNAPSHOT"),
        ),
        admin=AdminConfig(
            email=_require_env("ADMIN_EMAIL"),
            password=_require_env("ADMIN_PASSWORD"),
        ),
    )
    return _CONFIG
