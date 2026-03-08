from __future__ import annotations

import base64
import dataclasses
import datetime as dt
import enum
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..analysis_env import ensure_analysis_workspace_layout
from ..config import load_config
from ..daytona_backend import (
    delete_daytona_sandbox_for_thread,
    ensure_daytona_configured,
    ensure_daytona_thread_environment,
)
from ..deps import get_db, get_current_user
from langchain_core.messages.base import BaseMessage

from ..checkpointer_mysql import MySQLSaver
from ..models import Thread, User
from ..schemas import ThreadCreate, ThreadOut, ThreadUpdate
from ..workspace_paths import user_workspace_path

router = APIRouter(prefix="/threads", tags=["threads"])


def _ensure_workspace_layout(username: str) -> str:
    workspace = user_workspace_path(username, create=True)
    ensure_analysis_workspace_layout(str(workspace))
    return str(workspace)


def _to_utc_aware(value: dt.datetime) -> dt.datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=dt.timezone.utc)
    return value.astimezone(dt.timezone.utc)


def _to_out(thread: Thread) -> ThreadOut:
    return ThreadOut(
        thread_id=thread.id,
        user_id=thread.user_id,
        status=thread.status,
        title=thread.title,
        metadata=thread.metadata_json,
        thread_values=thread.thread_values,
        created_at=_to_utc_aware(thread.created_at),
        updated_at=_to_utc_aware(thread.updated_at),
    )


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, enum.Enum):
        return value.value
    if isinstance(value, bytes):
        return {"__type__": "bytes", "base64": base64.b64encode(value).decode("ascii")}
    if isinstance(value, bytearray):
        return {"__type__": "bytes", "base64": base64.b64encode(bytes(value)).decode("ascii")}
    if dataclasses.is_dataclass(value):
        return _json_safe(dataclasses.asdict(value))
    if isinstance(value, dict):
        return {k: _json_safe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_json_safe(v) for v in value]
    if isinstance(value, tuple):
        return [_json_safe(v) for v in value]
    if hasattr(value, "model_dump"):
        try:
            return _json_safe(value.model_dump())
        except Exception:
            pass
    # Fallback: represent unknown objects safely
    return {"__type__": value.__class__.__name__, "repr": repr(value)}


def _normalize_interrupts(checkpoint: dict[str, Any]) -> dict[str, Any]:
    channel_values = checkpoint.get("channel_values")
    if not isinstance(channel_values, dict):
        return checkpoint
    interrupts = channel_values.get("__interrupt__")
    if not isinstance(interrupts, (list, tuple)):
        return checkpoint

    normalized = []
    for item in interrupts:
        if hasattr(item, "value"):
            normalized.append(
                {
                    "value": getattr(item, "value"),
                    "id": getattr(item, "id", None),
                }
            )
        elif isinstance(item, dict) and "value" in item:
            normalized.append(item)
        else:
            normalized.append({"value": item, "id": None})

    return {**checkpoint, "channel_values": {**channel_values, "__interrupt__": normalized}}


@router.get("", response_model=list[ThreadOut])
def list_threads(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    threads = (
        db.query(Thread)
        .filter(Thread.user_id == user.id)
        .order_by(Thread.updated_at.desc())
        .all()
    )
    return [_to_out(t) for t in threads]


@router.get("/{thread_id}", response_model=ThreadOut)
def get_thread(
    thread_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    thread = db.get(Thread, thread_id)
    if not thread or thread.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Thread not found")
    return _to_out(thread)


@router.post("", response_model=ThreadOut)
def create_thread(
    payload: ThreadCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    cfg = load_config()
    try:
        _ensure_workspace_layout(user.username)
        ensure_daytona_configured()
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied",
        ) from e
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to initialize session environment: {e}",
        ) from e

    now = dt.datetime.utcnow()
    title = payload.title or f"Thread {now.date().isoformat()}"
    thread = Thread(
        user_id=user.id,
        status="idle",
        title=title,
        metadata_json=payload.metadata or {},
        thread_values={},
        created_at=now,
        updated_at=now,
    )
    db.add(thread)
    db.commit()
    db.refresh(thread)

    try:
        ensure_daytona_thread_environment(
            thread_id=thread.id,
            command_timeout_seconds=cfg.sandbox.time_limit_sec,
        )
    except Exception as e:
        # Avoid keeping a half-initialized thread when remote sandbox prep fails.
        delete_daytona_sandbox_for_thread(thread.id)
        db.delete(thread)
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to initialize Daytona environment: {e}",
        ) from e

    return _to_out(thread)


@router.patch("/{thread_id}", response_model=ThreadOut)
def update_thread(
    thread_id: str,
    payload: ThreadUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    thread = db.get(Thread, thread_id)
    if not thread or thread.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Thread not found")

    if payload.title is not None:
        thread.title = payload.title
    if payload.status is not None:
        thread.status = payload.status
    if payload.metadata is not None:
        thread.metadata_json = payload.metadata
    if payload.thread_values is not None:
        thread.thread_values = payload.thread_values

    thread.updated_at = dt.datetime.utcnow()
    db.commit()
    db.refresh(thread)
    return _to_out(thread)


@router.delete("/{thread_id}")
def delete_thread(
    thread_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    thread = db.get(Thread, thread_id)
    if not thread or thread.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Thread not found")

    delete_daytona_sandbox_for_thread(thread_id)

    db.delete(thread)
    db.commit()
    try:
        MySQLSaver().delete_thread(thread_id)
    except Exception:
        pass
    return {"success": True}


@router.get("/{thread_id}/history")
def thread_history(
    thread_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    thread = db.get(Thread, thread_id)
    if not thread or thread.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Thread not found")
    checkpointer = MySQLSaver()
    config = {"configurable": {"thread_id": thread_id}}
    history = []
    for item in checkpointer.list(config, limit=50):
        checkpoint = item.checkpoint
        channel_values = checkpoint.get("channel_values", {})
        messages = channel_values.get("messages")

        if isinstance(messages, list):
            normalized = []
            for msg in messages:
                if isinstance(msg, BaseMessage):
                    normalized.append(
                        {
                            "id": getattr(msg, "id", None),
                            "type": msg.type,
                            "content": msg.content,
                            "tool_calls": getattr(msg, "tool_calls", None),
                            "tool_call_id": getattr(msg, "tool_call_id", None),
                            "name": getattr(msg, "name", None),
                        }
                    )
                elif isinstance(msg, dict) and "type" in msg and "data" in msg:
                    data = msg.get("data") or {}
                    normalized.append(
                        {
                            "id": data.get("id"),
                            "type": msg.get("type"),
                            "content": data.get("content"),
                            "tool_calls": data.get("tool_calls"),
                            "tool_call_id": data.get("tool_call_id"),
                            "name": data.get("name"),
                        }
                    )
                elif isinstance(msg, dict):
                    normalized.append(msg)
            channel_values = {**channel_values, "messages": normalized}
            checkpoint = {**checkpoint, "channel_values": channel_values}

        checkpoint = _normalize_interrupts(checkpoint)

        history.append(
            {
                "checkpoint_id": item.config["configurable"]["checkpoint_id"],
                "checkpoint": _json_safe(checkpoint),
                "metadata": _json_safe(item.metadata),
                "pending_writes": _json_safe(item.pending_writes),
            }
        )
    return history


@router.post("/generate-title")
def generate_title(payload: dict, user: User = Depends(get_current_user)):
    message = payload.get("message") or payload.get("content") or ""
    if not message:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Message required")
    # Simple fallback: first 6 words
    words = message.strip().split()
    return {"title": " ".join(words[:6]) if words else "Untitled"}
