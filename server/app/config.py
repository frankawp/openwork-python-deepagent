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
class SandboxConfig:
    enabled: bool
    nsjail_path: str
    allow_local_fallback: bool
    disable_clone_newns: bool
    rootfs_dir: str
    readonly_bind_mounts: list[str]
    mount_dev: bool
    mount_proc: bool
    rlimit_as_mb: int
    rlimit_cpu_sec: int
    rlimit_fsize_mb: int
    time_limit_sec: int
    max_output_bytes: int
    seccomp_profile: str
    seccomp_profiles: dict[str, str]
    seccomp: str


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
    sandbox_raw = raw.get("sandbox") or {}
    seccomp_profile = str(sandbox_raw.get("seccomp_profile", "strict"))
    seccomp_profiles = sandbox_raw.get("seccomp_profiles") or {}
    seccomp_value = str(sandbox_raw.get("seccomp", ""))
    if seccomp_profiles:
        if seccomp_profile not in seccomp_profiles:
            raise ValueError(f"Unknown seccomp profile: {seccomp_profile}")
        seccomp_value = str(seccomp_profiles.get(seccomp_profile, ""))

    _CONFIG = AppConfig(
        database=DatabaseConfig(url=_require_key(db_raw, "url")),
        auth=AuthConfig(
            jwt_secret=_require_key(auth_raw, "jwt_secret"),
            access_ttl_min=int(_require_key(auth_raw, "access_ttl_min")),
            refresh_ttl_days=int(_require_key(auth_raw, "refresh_ttl_days")),
        ),
        workspace=WorkspaceConfig(root=_require_key(workspace_raw, "root")),
        data=DataConfig(dir=_require_key(data_raw, "dir")),
        sandbox=SandboxConfig(
            enabled=bool(sandbox_raw.get("enabled", True)),
            nsjail_path=str(sandbox_raw.get("nsjail_path", "nsjail")),
            allow_local_fallback=bool(sandbox_raw.get("allow_local_fallback", False)),
            disable_clone_newns=bool(sandbox_raw.get("disable_clone_newns", False)),
            rootfs_dir=str(sandbox_raw.get("rootfs_dir", ".sandbox-root")),
            readonly_bind_mounts=list(
                sandbox_raw.get(
                    "readonly_bind_mounts",
                    ["/bin", "/usr", "/usr/local", "/lib", "/lib64", "/etc"],
                )
            ),
            mount_dev=bool(sandbox_raw.get("mount_dev", True)),
            mount_proc=bool(sandbox_raw.get("mount_proc", False)),
            rlimit_as_mb=int(sandbox_raw.get("rlimit_as_mb", 2048)),
            rlimit_cpu_sec=int(sandbox_raw.get("rlimit_cpu_sec", 120)),
            rlimit_fsize_mb=int(sandbox_raw.get("rlimit_fsize_mb", 512)),
            time_limit_sec=int(sandbox_raw.get("time_limit_sec", 120)),
            max_output_bytes=int(sandbox_raw.get("max_output_bytes", 100_000)),
            seccomp_profile=seccomp_profile,
            seccomp_profiles={
                str(key): str(value) for key, value in seccomp_profiles.items()
            },
            seccomp=seccomp_value,
        ),
        admin=AdminConfig(
            email=_require_key(admin_raw, "email"),
            password=_require_key(admin_raw, "password"),
        ),
    )
    return _CONFIG
