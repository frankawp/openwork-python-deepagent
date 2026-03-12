from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
import yaml

from ..checkpointer_mysql import MySQLSaver
from ..deps import get_current_user, get_db
from ..models import Skill, SkillFile, User
from ..schemas import (
    SkillCreate,
    SkillFileDetailOut,
    SkillFileUpsert,
    SkillOut,
    SkillUpdate,
)
from ..skills_service import (
    SKILL_FILE_REQUIRED,
    content_checksum,
    normalize_skill_file_path,
    normalize_skill_key,
    sync_user_skill_bindings,
    validate_skill_markdown,
)

router = APIRouter(prefix="/skills", tags=["skills"])


def _clear_skills_metadata_cache(thread_ids: list[str]) -> None:
    if not thread_ids:
        return
    checkpointer = MySQLSaver()
    for thread_id in sorted(set(thread_ids)):
        checkpointer.clear_channel_value(thread_id, "skills_metadata")


def _to_skill_out(skill: Skill) -> SkillOut:
    return SkillOut(
        id=skill.id,
        user_id=skill.user_id,
        key=skill.key,
        name=skill.name,
        description=skill.description,
        enabled=skill.enabled,
        created_at=skill.created_at,
        updated_at=skill.updated_at,
    )


def _to_file_detail_out(file: SkillFile) -> SkillFileDetailOut:
    return SkillFileDetailOut(
        id=file.id,
        skill_id=file.skill_id,
        path=file.path,
        checksum=file.checksum,
        updated_at=file.updated_at,
        content=file.content,
    )


def _must_get_user_skill(db: Session, skill_id: str, user_id: str) -> Skill:
    skill = db.get(Skill, skill_id)
    if not skill or skill.user_id != user_id:
        raise HTTPException(status_code=404, detail="Skill not found")
    return skill


def _default_skill_markdown(skill: Skill) -> str:
    frontmatter = yaml.safe_dump(
        {"name": skill.key, "description": skill.description},
        sort_keys=False,
        allow_unicode=True,
    ).strip()
    return f"---\n{frontmatter}\n---\n\n# {skill.name}\n\nDescribe when and how to use this skill.\n"


@router.get("", response_model=list[SkillOut])
def list_skills(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    skills = (
        db.query(Skill)
        .filter(Skill.user_id == user.id)
        .order_by(Skill.updated_at.desc())
        .all()
    )
    return [_to_skill_out(skill) for skill in skills]


@router.post("", response_model=SkillOut)
def create_skill(
    payload: SkillCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    now = dt.datetime.utcnow()
    key = normalize_skill_key(payload.key)
    skill = Skill(
        user_id=user.id,
        key=key,
        name=payload.name.strip(),
        description=payload.description.strip(),
        enabled=payload.enabled,
        created_at=now,
        updated_at=now,
    )
    skill_md_content = _default_skill_markdown(skill)
    validate_skill_markdown(skill_md_content, expected_key=key)
    skill_file = SkillFile(
        skill=skill,
        path=SKILL_FILE_REQUIRED,
        content=skill_md_content,
        checksum=content_checksum(skill_md_content),
        updated_at=now,
    )
    db.add(skill)
    db.add(skill_file)
    affected_thread_ids: list[str] = []
    try:
        db.flush()
        affected_thread_ids = sync_user_skill_bindings(db, user_id=user.id)
        db.commit()
    except IntegrityError as e:
        db.rollback()
        raise HTTPException(status_code=409, detail="Skill key already exists") from e
    db.refresh(skill)
    _clear_skills_metadata_cache(affected_thread_ids)
    return _to_skill_out(skill)


@router.get("/{skill_id}", response_model=SkillOut)
def get_skill(skill_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    skill = _must_get_user_skill(db, skill_id, user.id)
    return _to_skill_out(skill)


@router.patch("/{skill_id}", response_model=SkillOut)
def update_skill(
    skill_id: str,
    payload: SkillUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    skill = _must_get_user_skill(db, skill_id, user.id)
    changed = False
    if payload.name is not None:
        skill.name = payload.name.strip()
        changed = True
    if payload.description is not None:
        skill.description = payload.description.strip()
        changed = True
    if payload.enabled is not None:
        skill.enabled = payload.enabled
        changed = True

    if changed:
        skill.updated_at = dt.datetime.utcnow()
        affected_thread_ids = sync_user_skill_bindings(db, user_id=user.id)
        db.commit()
        db.refresh(skill)
        _clear_skills_metadata_cache(affected_thread_ids)
    return _to_skill_out(skill)


@router.delete("/{skill_id}")
def delete_skill(skill_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    skill = _must_get_user_skill(db, skill_id, user.id)
    db.delete(skill)
    db.flush()
    affected_thread_ids = sync_user_skill_bindings(db, user_id=user.id)
    db.commit()
    _clear_skills_metadata_cache(affected_thread_ids)
    return {"success": True}


@router.get("/{skill_id}/files", response_model=list[SkillFileDetailOut])
def list_skill_files(
    skill_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    skill = _must_get_user_skill(db, skill_id, user.id)
    files = (
        db.query(SkillFile)
        .filter(SkillFile.skill_id == skill.id)
        .order_by(SkillFile.path.asc())
        .all()
    )
    return [_to_file_detail_out(file) for file in files]


@router.put("/{skill_id}/files", response_model=SkillFileDetailOut)
def upsert_skill_file(
    skill_id: str,
    payload: SkillFileUpsert,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    skill = _must_get_user_skill(db, skill_id, user.id)
    path = normalize_skill_file_path(payload.path)
    content = payload.content
    if path == SKILL_FILE_REQUIRED:
        validate_skill_markdown(content, expected_key=skill.key)

    now = dt.datetime.utcnow()
    file = (
        db.query(SkillFile)
        .filter(SkillFile.skill_id == skill.id, SkillFile.path == path)
        .first()
    )
    checksum = content_checksum(content)
    if file:
        file.content = content
        file.checksum = checksum
        file.updated_at = now
    else:
        file = SkillFile(
            skill_id=skill.id,
            path=path,
            content=content,
            checksum=checksum,
            updated_at=now,
        )
        db.add(file)

    skill.updated_at = now
    affected_thread_ids = sync_user_skill_bindings(db, user_id=user.id)
    db.commit()
    db.refresh(file)
    _clear_skills_metadata_cache(affected_thread_ids)
    return _to_file_detail_out(file)


@router.delete("/{skill_id}/files")
def delete_skill_file(
    skill_id: str,
    path: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    skill = _must_get_user_skill(db, skill_id, user.id)
    normalized = normalize_skill_file_path(path)
    if normalized == SKILL_FILE_REQUIRED:
        raise HTTPException(status_code=400, detail="SKILL.md cannot be deleted")

    file = (
        db.query(SkillFile)
        .filter(SkillFile.skill_id == skill.id, SkillFile.path == normalized)
        .first()
    )
    if not file:
        raise HTTPException(status_code=404, detail="Skill file not found")

    db.delete(file)
    skill.updated_at = dt.datetime.utcnow()
    affected_thread_ids = sync_user_skill_bindings(db, user_id=user.id)
    db.commit()
    _clear_skills_metadata_cache(affected_thread_ids)
    return {"success": True}
