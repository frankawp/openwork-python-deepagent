from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload

from ..checkpointer_mysql import MySQLSaver
from ..deps import get_current_user, get_db
from ..models import Skill, ThreadSkillBinding, ThreadSkillMaterializationState, User
from ..schemas import (
    ThreadSkillBindingOut,
    ThreadSkillBindingSet,
    ThreadSkillMaterializationStateOut,
)
from ..skills_service import ensure_thread_owned, update_thread_materialization_state

router = APIRouter(prefix="/thread-skills", tags=["thread-skills"])


def _require_owned_thread(db: Session, *, thread_id: str, user_id: str) -> None:
    try:
        ensure_thread_owned(db, thread_id=thread_id, user_id=user_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


def _to_binding_out(binding: ThreadSkillBinding) -> ThreadSkillBindingOut:
    skill = binding.skill
    assert skill is not None
    return ThreadSkillBindingOut(
        id=binding.id,
        thread_id=binding.thread_id,
        skill_id=binding.skill_id,
        position=binding.position,
        enabled=binding.enabled,
        created_at=binding.created_at,
        updated_at=binding.updated_at,
        skill={
            "id": skill.id,
            "user_id": skill.user_id,
            "key": skill.key,
            "name": skill.name,
            "description": skill.description,
            "enabled": skill.enabled,
            "created_at": skill.created_at,
            "updated_at": skill.updated_at,
        },
    )


def _to_materialization_out(
    state: ThreadSkillMaterializationState | None,
    thread_id: str,
) -> ThreadSkillMaterializationStateOut:
    now = dt.datetime.utcnow()
    if not state:
        return ThreadSkillMaterializationStateOut(
            thread_id=thread_id,
            desired_hash=None,
            materialized_hash=None,
            status="ready",
            materialized_root=None,
            last_error=None,
            updated_at=now,
        )
    return ThreadSkillMaterializationStateOut(
        thread_id=state.thread_id,
        desired_hash=state.desired_hash,
        materialized_hash=state.materialized_hash,
        status=state.status,
        materialized_root=state.materialized_root,
        last_error=state.last_error,
        updated_at=state.updated_at,
    )


@router.get("/{thread_id}", response_model=list[ThreadSkillBindingOut])
def list_thread_skills(
    thread_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _require_owned_thread(db, thread_id=thread_id, user_id=user.id)
    bindings = (
        db.query(ThreadSkillBinding)
        .options(joinedload(ThreadSkillBinding.skill))
        .join(Skill, ThreadSkillBinding.skill_id == Skill.id)
        .filter(ThreadSkillBinding.thread_id == thread_id, Skill.user_id == user.id)
        .order_by(ThreadSkillBinding.position.asc())
        .all()
    )
    return [_to_binding_out(binding) for binding in bindings]


@router.put("/{thread_id}", response_model=list[ThreadSkillBindingOut])
def set_thread_skills(
    thread_id: str,
    payload: ThreadSkillBindingSet,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _require_owned_thread(db, thread_id=thread_id, user_id=user.id)
    skill_ids = payload.skill_ids
    if len(set(skill_ids)) != len(skill_ids):
        raise HTTPException(status_code=400, detail="Duplicate skill ids are not allowed")

    if skill_ids:
        owned_count = (
            db.query(Skill).filter(Skill.user_id == user.id, Skill.id.in_(skill_ids)).count()
        )
        if owned_count != len(skill_ids):
            raise HTTPException(status_code=400, detail="One or more skills are invalid")

    db.query(ThreadSkillBinding).filter(ThreadSkillBinding.thread_id == thread_id).delete()

    now = dt.datetime.utcnow()
    for idx, skill_id in enumerate(skill_ids):
        db.add(
            ThreadSkillBinding(
                thread_id=thread_id,
                skill_id=skill_id,
                position=idx,
                enabled=True,
                created_at=now,
                updated_at=now,
            )
        )

    # SessionLocal is configured with autoflush=False, so flush before state derivation.
    db.flush()
    update_thread_materialization_state(db, thread_id)
    db.commit()
    # Invalidate persisted skills cache so middleware reloads from new bindings.
    MySQLSaver().clear_channel_value(thread_id, "skills_metadata")

    bindings = (
        db.query(ThreadSkillBinding)
        .options(joinedload(ThreadSkillBinding.skill))
        .join(Skill, ThreadSkillBinding.skill_id == Skill.id)
        .filter(ThreadSkillBinding.thread_id == thread_id, Skill.user_id == user.id)
        .order_by(ThreadSkillBinding.position.asc())
        .all()
    )
    return [_to_binding_out(binding) for binding in bindings]


@router.delete("/{thread_id}/{skill_id}")
def remove_thread_skill(
    thread_id: str,
    skill_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _require_owned_thread(db, thread_id=thread_id, user_id=user.id)
    skill = db.get(Skill, skill_id)
    if not skill or skill.user_id != user.id:
        raise HTTPException(status_code=404, detail="Skill not found")

    binding = (
        db.query(ThreadSkillBinding)
        .filter(ThreadSkillBinding.thread_id == thread_id, ThreadSkillBinding.skill_id == skill_id)
        .first()
    )
    if not binding:
        return {"success": True}

    db.delete(binding)
    # Normalize position order.
    bindings = (
        db.query(ThreadSkillBinding)
        .filter(ThreadSkillBinding.thread_id == thread_id)
        .order_by(ThreadSkillBinding.position.asc())
        .all()
    )
    now = dt.datetime.utcnow()
    for idx, row in enumerate(bindings):
        row.position = idx
        row.updated_at = now

    # SessionLocal is configured with autoflush=False, so flush before state derivation.
    db.flush()
    update_thread_materialization_state(db, thread_id)
    db.commit()
    # Invalidate persisted skills cache so middleware reloads after unbinding.
    MySQLSaver().clear_channel_value(thread_id, "skills_metadata")
    return {"success": True}


@router.get(
    "/{thread_id}/materialization",
    response_model=ThreadSkillMaterializationStateOut,
)
def get_thread_skill_materialization(
    thread_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _require_owned_thread(db, thread_id=thread_id, user_id=user.id)
    state = db.get(ThreadSkillMaterializationState, thread_id)
    return _to_materialization_out(state, thread_id)
