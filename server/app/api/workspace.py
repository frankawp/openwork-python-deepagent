from __future__ import annotations

import base64
import json
import os
from pathlib import Path
from typing import Any, AsyncGenerator

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from watchfiles import awatch

from ..checkpointer_mysql import MySQLSaver
from ..config import load_config
from ..deps import get_current_user
from ..schemas import WorkspaceListOut, WorkspaceReadOut
from ..models import User

router = APIRouter(prefix="/workspace", tags=["workspace"])


def _workspace_root() -> Path:
    cfg = load_config()
    return Path(cfg.workspace.root).resolve()


def _user_workspace(user: User) -> Path:
    root = _workspace_root()
    return (root / user.username).resolve()


def _ensure_workspace(user: User) -> Path:
    path = _user_workspace(user)
    path.mkdir(parents=True, exist_ok=True)
    return path


def _safe_path(workspace: Path, rel_path: str) -> Path:
    rel = rel_path.lstrip("/")
    full = (workspace / rel).resolve()
    if not str(full).startswith(str(workspace)):
        raise HTTPException(status_code=403, detail="Access denied")
    return full


def _file_data_to_string(file_data: Any) -> str:
    if isinstance(file_data, dict):
        content = file_data.get("content")
        if isinstance(content, list):
            return "\n".join(str(line) for line in content)
        if isinstance(content, str):
            return content
    if isinstance(file_data, list):
        return "\n".join(str(line) for line in file_data)
    if isinstance(file_data, str):
        return file_data
    return ""


@router.get("")
def get_workspace(user: User = Depends(get_current_user)):
    path = _ensure_workspace(user)
    return {"path": str(path)}


@router.get("/files", response_model=WorkspaceListOut)
def list_files(thread_id: str, user: User = Depends(get_current_user)):
    workspace = _ensure_workspace(user)
    files = []

    for root, dirs, filenames in os.walk(workspace):
        dirs[:] = [d for d in dirs if not d.startswith(".") and d != "node_modules"]
        for d in dirs:
            rel = Path(root, d).relative_to(workspace)
            files.append({"path": f"/{rel.as_posix()}", "is_dir": True})
        for filename in filenames:
            if filename.startswith("."):
                continue
            full = Path(root) / filename
            rel = full.relative_to(workspace)
            stat = full.stat()
            files.append(
                {
                    "path": f"/{rel.as_posix()}",
                    "is_dir": False,
                    "size": stat.st_size,
                    "modified_at": str(stat.st_mtime),
                }
            )

    return {"success": True, "files": files, "workspacePath": str(workspace)}


@router.get("/file", response_model=WorkspaceReadOut)
def read_file(thread_id: str, path: str, user: User = Depends(get_current_user)):
    workspace = _ensure_workspace(user)
    full = _safe_path(workspace, path)
    if full.is_dir():
        return {"success": False, "error": "Cannot read directory"}

    try:
        content = full.read_text("utf-8")
    except Exception as e:
        return {"success": False, "error": str(e)}

    stat = full.stat()
    return {
        "success": True,
        "content": content,
        "size": stat.st_size,
        "modified_at": str(stat.st_mtime),
    }


@router.get("/file-binary", response_model=WorkspaceReadOut)
def read_file_binary(thread_id: str, path: str, user: User = Depends(get_current_user)):
    workspace = _ensure_workspace(user)
    full = _safe_path(workspace, path)
    if full.is_dir():
        return {"success": False, "error": "Cannot read directory"}

    try:
        data = full.read_bytes()
        content = base64.b64encode(data).decode("utf-8")
    except Exception as e:
        return {"success": False, "error": str(e)}

    stat = full.stat()
    return {
        "success": True,
        "content": content,
        "size": stat.st_size,
        "modified_at": str(stat.st_mtime),
    }


@router.post("/sync")
def sync_to_disk(payload: dict, user: User = Depends(get_current_user)):
    thread_id = payload.get("thread_id") or payload.get("threadId")
    if not thread_id:
        raise HTTPException(status_code=400, detail="thread_id is required")

    workspace = _ensure_workspace(user)
    checkpointer = MySQLSaver()
    config = {"configurable": {"thread_id": thread_id}}
    checkpoint_tuple = checkpointer.get_tuple(config)

    if not checkpoint_tuple:
        return {"success": True, "written": 0, "errors": [], "message": "No checkpoint"}

    checkpoint = checkpoint_tuple.checkpoint or {}
    files = None

    if isinstance(checkpoint, dict):
        channel_values = checkpoint.get("channel_values")
        if isinstance(channel_values, dict):
            files = channel_values.get("files")
        if files is None:
            files = checkpoint.get("files")

    if not isinstance(files, dict):
        return {"success": True, "written": 0, "errors": [], "message": "No files to sync"}

    written = 0
    errors: list[dict[str, str]] = []

    for path, file_data in files.items():
        if not isinstance(path, str):
            continue
        if path in ("", "/"):
            continue

        try:
            full = _safe_path(workspace, path)
            if path.endswith("/"):
                full.mkdir(parents=True, exist_ok=True)
                continue
            full.parent.mkdir(parents=True, exist_ok=True)
            content = _file_data_to_string(file_data)
            full.write_text(content, "utf-8")
            written += 1
        except Exception as e:
            errors.append({"path": str(path), "error": str(e)})

    return {"success": len(errors) == 0, "written": written, "errors": errors}


async def _watch_workspace(workspace: Path, thread_id: str) -> AsyncGenerator[str, None]:
    async for changes in awatch(workspace):
        for _change, path in changes:
            if "/." in path or "/node_modules/" in path:
                continue
        payload = {
            "type": "files-changed",
            "threadId": thread_id,
            "workspacePath": str(workspace),
        }
        yield f"data: {json.dumps(payload)}\n\n"


@router.get("/changes")
def watch_changes(thread_id: str, user: User = Depends(get_current_user)):
    workspace = _ensure_workspace(user)
    return StreamingResponse(_watch_workspace(workspace, thread_id), media_type="text/event-stream")
