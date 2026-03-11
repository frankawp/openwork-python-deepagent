from __future__ import annotations

import datetime as dt
import hashlib
import json
import posixpath
import re
from dataclasses import dataclass
from typing import Any

import yaml
from sqlalchemy import Select, select
from sqlalchemy.orm import Session, joinedload

from .config import load_config
from .daytona_backend import get_or_create_daytona_backend
from .models import (
    Skill,
    SkillFile,
    Thread,
    ThreadSkillBinding,
    ThreadSkillMaterializationState,
)

SKILL_FILE_REQUIRED = "SKILL.md"
SKILL_MATERIALIZATION_BASE = "/home/daytona/.openwork/skills/thread"

STATUS_DIRTY = "dirty"
STATUS_SYNCING = "syncing"
STATUS_READY = "ready"
STATUS_FAILED = "failed"
VALID_STATUSES = {STATUS_DIRTY, STATUS_SYNCING, STATUS_READY, STATUS_FAILED}

SKILL_KEY_PATTERN = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,62}[a-z0-9])?$")


@dataclass(frozen=True)
class MaterializationClaim:
    thread_id: str
    desired_hash: str


def utcnow() -> dt.datetime:
    return dt.datetime.utcnow()


def normalize_skill_key(key: str) -> str:
    normalized = (key or "").strip().lower()
    if not SKILL_KEY_PATTERN.fullmatch(normalized):
        raise ValueError(
            "Invalid skill key. Use lowercase letters, digits, hyphen, length 1-64."
        )
    return normalized


def normalize_skill_file_path(path: str) -> str:
    raw = (path or "").strip()
    if not raw:
        raise ValueError("File path is required")

    normalized = posixpath.normpath(raw.replace("\\", "/"))
    if normalized.startswith("/") or normalized in {".", ".."} or normalized.startswith("../"):
        raise ValueError("File path must be a relative path inside the skill directory")
    if "/../" in f"/{normalized}/":
        raise ValueError("File path cannot contain parent directory traversal")
    return normalized


def content_checksum(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def validate_skill_markdown(content: str, *, expected_key: str | None = None) -> None:
    match = re.match(r"^---\s*\n(.*?)\n---\s*\n", content, re.DOTALL)
    if not match:
        raise ValueError("SKILL.md must include YAML frontmatter")

    try:
        meta = yaml.safe_load(match.group(1))
    except yaml.YAMLError as e:
        raise ValueError(f"Invalid SKILL.md frontmatter YAML: {e}") from e

    if not isinstance(meta, dict):
        raise ValueError("SKILL.md frontmatter must be a mapping")

    name = str(meta.get("name", "")).strip()
    description = str(meta.get("description", "")).strip()
    if not name or not description:
        raise ValueError("SKILL.md frontmatter requires non-empty 'name' and 'description'")

    if expected_key and name != expected_key:
        raise ValueError(f"SKILL.md frontmatter 'name' must equal skill key '{expected_key}'")


def ensure_thread_owned(db: Session, *, thread_id: str, user_id: str) -> Thread:
    thread = db.get(Thread, thread_id)
    if not thread or thread.user_id != user_id:
        raise ValueError("Thread not found")
    return thread


def ensure_skill_owned(db: Session, *, skill_id: str, user_id: str) -> Skill:
    skill = db.get(Skill, skill_id)
    if not skill or skill.user_id != user_id:
        raise ValueError("Skill not found")
    return skill


def _bindings_with_skills_query(thread_id: str) -> Select[Any]:
    return (
        select(ThreadSkillBinding)
        .options(joinedload(ThreadSkillBinding.skill).joinedload(Skill.files))
        .where(ThreadSkillBinding.thread_id == thread_id, ThreadSkillBinding.enabled.is_(True))
        .order_by(ThreadSkillBinding.position.asc())
    )


def _enabled_bindings_with_valid_skills(db: Session, thread_id: str) -> list[ThreadSkillBinding]:
    bindings = db.execute(_bindings_with_skills_query(thread_id)).unique().scalars().all()
    return [b for b in bindings if b.skill and b.skill.enabled]


def _get_skill_md_file(skill: Skill) -> SkillFile | None:
    for f in skill.files:
        if f.path == SKILL_FILE_REQUIRED:
            return f
    return None


def _build_desired_hash(bindings: list[ThreadSkillBinding]) -> str | None:
    if not bindings:
        return None

    payload: list[dict[str, Any]] = []
    for b in bindings:
        skill = b.skill
        if not skill:
            continue
        files = sorted(skill.files, key=lambda x: x.path)
        payload.append(
            {
                "skill_id": skill.id,
                "skill_key": skill.key,
                "position": b.position,
                "files": [{"path": f.path, "checksum": f.checksum} for f in files],
            }
        )

    serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def update_thread_materialization_state(db: Session, thread_id: str) -> ThreadSkillMaterializationState:
    bindings = _enabled_bindings_with_valid_skills(db, thread_id)
    desired_hash = _build_desired_hash(bindings)

    state = db.get(ThreadSkillMaterializationState, thread_id)
    if not state:
        state = ThreadSkillMaterializationState(
            thread_id=thread_id,
            status=STATUS_READY,
            updated_at=utcnow(),
        )
        db.add(state)

    state.desired_hash = desired_hash
    state.updated_at = utcnow()

    if desired_hash is None:
        state.materialized_hash = None
        state.materialized_root = None
        state.status = STATUS_READY
        state.last_error = None
        return state

    if state.materialized_hash == desired_hash:
        state.status = STATUS_READY
        state.last_error = None
    elif state.status != STATUS_SYNCING:
        state.status = STATUS_DIRTY
    return state


def update_materialization_state_for_skill(db: Session, skill_id: str) -> None:
    thread_ids = (
        db.execute(
            select(ThreadSkillBinding.thread_id).where(
                ThreadSkillBinding.skill_id == skill_id,
                ThreadSkillBinding.enabled.is_(True),
            )
        )
        .scalars()
        .all()
    )
    for thread_id in sorted(set(thread_ids)):
        update_thread_materialization_state(db, thread_id)


def claim_next_dirty_thread(db: Session) -> MaterializationClaim | None:
    row = (
        db.execute(
            select(ThreadSkillMaterializationState)
            .where(
                ThreadSkillMaterializationState.status == STATUS_DIRTY,
                ThreadSkillMaterializationState.desired_hash.is_not(None),
            )
            .order_by(ThreadSkillMaterializationState.updated_at.asc())
            .with_for_update(skip_locked=True)
            .limit(1)
        )
        .scalars()
        .first()
    )
    if not row or not row.desired_hash:
        return None

    row.status = STATUS_SYNCING
    row.last_error = None
    row.updated_at = utcnow()
    return MaterializationClaim(thread_id=row.thread_id, desired_hash=row.desired_hash)


def _materialization_root(thread_id: str, desired_hash: str) -> str:
    return f"{SKILL_MATERIALIZATION_BASE}/{thread_id}/{desired_hash}"


def build_materialization_file_payload(
    db: Session,
    *,
    thread_id: str,
    desired_hash: str,
) -> tuple[str, list[tuple[str, bytes]]]:
    bindings = _enabled_bindings_with_valid_skills(db, thread_id)
    current_hash = _build_desired_hash(bindings)
    if not current_hash or current_hash != desired_hash:
        raise ValueError("Desired hash changed during materialization")

    uploads: list[tuple[str, bytes]] = []
    root = _materialization_root(thread_id, desired_hash)
    for binding in bindings:
        skill = binding.skill
        if not skill:
            continue

        skill_md = _get_skill_md_file(skill)
        if not skill_md:
            raise ValueError(f"Skill '{skill.key}' is missing SKILL.md")
        validate_skill_markdown(skill_md.content, expected_key=skill.key)

        for f in skill.files:
            normalized = normalize_skill_file_path(f.path)
            destination = posixpath.join(root, skill.key, normalized)
            uploads.append((destination, f.content.encode("utf-8")))

    return root, uploads


def materialize_thread_skills(
    *,
    thread_id: str,
    desired_hash: str,
    files: list[tuple[str, bytes]],
) -> str:
    cfg = load_config()
    context = get_or_create_daytona_backend(
        thread_id=thread_id,
        command_timeout_seconds=cfg.sandbox.time_limit_sec,
        allow_create_if_missing=False,
    )
    backend = context.backend
    root = _materialization_root(thread_id, desired_hash)

    if files:
        unique_dirs = sorted({posixpath.dirname(path) for path, _ in files})
        mkdir_script = " && ".join(
            [f"mkdir -p {json.dumps(directory)}" for directory in unique_dirs]
        )
        if mkdir_script:
            result = backend.execute(mkdir_script, timeout=max(cfg.sandbox.time_limit_sec, 20))
            if result.exit_code != 0:
                raise RuntimeError(f"Failed to create skill directories: {result.output}")

        responses = backend.upload_files(files)
        errors = [r for r in responses if getattr(r, "error", None)]
        if errors:
            err_text = ", ".join(
                [f"{getattr(e, 'path', '?')}: {getattr(e, 'error', 'unknown')}" for e in errors]
            )
            raise RuntimeError(f"Failed to upload skill files: {err_text}")

    return root


def finalize_materialization_success(
    db: Session,
    *,
    thread_id: str,
    desired_hash: str,
    materialized_root: str,
) -> None:
    state = db.get(ThreadSkillMaterializationState, thread_id)
    if not state:
        return

    state.materialized_hash = desired_hash
    state.materialized_root = materialized_root
    state.last_error = None
    state.updated_at = utcnow()

    if state.desired_hash == desired_hash:
        state.status = STATUS_READY
    else:
        state.status = STATUS_DIRTY


def finalize_materialization_failure(
    db: Session,
    *,
    thread_id: str,
    error: str,
) -> None:
    state = db.get(ThreadSkillMaterializationState, thread_id)
    if not state:
        return
    if state.desired_hash and state.materialized_hash != state.desired_hash:
        state.status = STATUS_DIRTY
    else:
        state.status = STATUS_FAILED
    state.last_error = error
    state.updated_at = utcnow()


def mark_materialization_dirty_if_needed(db: Session, *, thread_id: str) -> None:
    state = db.get(ThreadSkillMaterializationState, thread_id)
    if not state:
        return
    if state.desired_hash and state.materialized_hash != state.desired_hash:
        state.status = STATUS_DIRTY
        state.last_error = None
        state.updated_at = utcnow()


def get_runtime_skill_paths(
    db: Session,
    *,
    thread_id: str,
    skills_enabled: bool,
) -> list[str]:
    if not skills_enabled:
        return []

    state = db.get(ThreadSkillMaterializationState, thread_id)
    if not state:
        return []

    if state.status == STATUS_READY and state.materialized_root:
        return [state.materialized_root]

    if state.status in {STATUS_SYNCING, STATUS_DIRTY, STATUS_FAILED} and state.materialized_root:
        return [state.materialized_root]

    return []
