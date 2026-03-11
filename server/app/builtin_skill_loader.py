from __future__ import annotations

import datetime as dt
import re
from pathlib import Path

import yaml
from sqlalchemy.orm import Session

from .models import Skill, SkillFile
from .skills_service import (
    SKILL_FILE_REQUIRED,
    content_checksum,
    normalize_skill_file_path,
    normalize_skill_key,
    validate_skill_markdown,
)

BUILTIN_SKILL_KEYS = ("skill-creator", "skill-installer")
BUILTIN_SKILLS_ROOT = Path(__file__).resolve().parent / "builtin_skills"

_FRONTMATTER_PATTERN = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)


def _extract_frontmatter(skill_markdown: str) -> dict:
    match = _FRONTMATTER_PATTERN.match(skill_markdown)
    if not match:
        raise ValueError("SKILL.md must include YAML frontmatter")
    parsed = yaml.safe_load(match.group(1))
    if not isinstance(parsed, dict):
        raise ValueError("SKILL.md frontmatter must be a mapping")
    return parsed


def _load_skill_files(skill_key: str) -> dict[str, str]:
    skill_dir = BUILTIN_SKILLS_ROOT / skill_key
    if not skill_dir.exists():
        raise FileNotFoundError(f"Builtin skill directory not found: {skill_dir}")

    files: dict[str, str] = {}
    for path in sorted(skill_dir.rglob("*")):
        if not path.is_file():
            continue
        relative = normalize_skill_file_path(path.relative_to(skill_dir).as_posix())
        try:
            content = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            # Builtin skill files are expected to be text files.
            continue
        files[relative] = content

    if SKILL_FILE_REQUIRED not in files:
        raise ValueError(f"Builtin skill '{skill_key}' is missing {SKILL_FILE_REQUIRED}")

    return files


def ensure_builtin_skills_for_user(db: Session, *, user_id: str) -> list[str]:
    created: list[str] = []

    for raw_key in BUILTIN_SKILL_KEYS:
        skill_key = normalize_skill_key(raw_key)
        exists = (
            db.query(Skill.id)
            .filter(Skill.user_id == user_id, Skill.key == skill_key)
            .first()
        )
        if exists:
            continue

        files = _load_skill_files(skill_key)
        skill_md = files[SKILL_FILE_REQUIRED]
        validate_skill_markdown(skill_md, expected_key=skill_key)
        frontmatter = _extract_frontmatter(skill_md)
        description = str(frontmatter.get("description", "")).strip()
        if not description:
            raise ValueError(
                f"Builtin skill '{skill_key}' must provide frontmatter description"
            )

        now = dt.datetime.utcnow()
        skill = Skill(
            user_id=user_id,
            key=skill_key,
            name=skill_key,
            description=description,
            enabled=True,
            created_at=now,
            updated_at=now,
        )
        db.add(skill)
        db.flush()

        for relative_path, content in files.items():
            db.add(
                SkillFile(
                    skill_id=skill.id,
                    path=relative_path,
                    content=content,
                    checksum=content_checksum(content),
                    updated_at=now,
                )
            )
        created.append(skill_key)

    return created
