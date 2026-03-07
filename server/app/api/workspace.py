from __future__ import annotations

import base64
import posixpath
from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from ..config import load_config
from ..daytona_backend import ensure_daytona_configured, get_or_create_daytona_backend
from ..db import SessionLocal
from ..deps import get_current_user
from ..models import Thread, User
from ..schemas import WorkspaceListOut, WorkspaceReadOut

router = APIRouter(prefix="/workspace", tags=["workspace"])


def _get_owned_thread(thread_id: str, user: User) -> Thread:
    db = SessionLocal()
    try:
        thread = db.get(Thread, thread_id)
        if not thread or thread.user_id != user.id:
            raise HTTPException(status_code=404, detail="Thread not found")
        return thread
    finally:
        db.close()


def _get_daytona_context(thread_id: str):
    cfg = load_config()
    ensure_daytona_configured()
    return get_or_create_daytona_backend(
        thread_id=thread_id,
        command_timeout_seconds=cfg.sandbox.time_limit_sec,
    )


def _normalize_root(workspace_root: str) -> str:
    normalized = posixpath.normpath(workspace_root or "/")
    return normalized if normalized.startswith("/") else f"/{normalized}"


def _is_within_root(workspace_root: str, candidate_path: str) -> bool:
    root = _normalize_root(workspace_root)
    candidate = posixpath.normpath(candidate_path)
    if not candidate.startswith("/"):
        candidate = f"/{candidate}"
    if root == "/":
        return True
    return candidate == root or candidate.startswith(f"{root}/")


def _safe_sandbox_path(workspace_root: str, path: str) -> str:
    root = _normalize_root(workspace_root)
    raw = (path or "").strip()
    if not raw or raw == "/":
        return root

    if raw.startswith(root):
        candidate = posixpath.normpath(raw)
    elif raw.startswith("/"):
        candidate = posixpath.normpath(posixpath.join(root, raw.lstrip("/")))
    else:
        candidate = posixpath.normpath(posixpath.join(root, raw))

    if not candidate.startswith("/"):
        candidate = f"/{candidate}"

    if not _is_within_root(root, candidate):
        raise HTTPException(status_code=403, detail="Access denied")
    return candidate


def _to_relative_path(workspace_root: str, full_path: str) -> str:
    root = _normalize_root(workspace_root)
    normalized = posixpath.normpath(full_path)
    if normalized == root:
        return "/"
    rel = posixpath.relpath(normalized, root)
    if rel == ".":
        return "/"
    return f"/{rel.lstrip('/')}"


def _is_hidden_or_ignored(path: str) -> bool:
    parts = [p for p in path.split("/") if p]
    for part in parts:
        if part.startswith(".") or part == "node_modules":
            return True
    return False


def _list_workspace_files(backend: Any, workspace_root: str) -> list[dict[str, Any]]:
    files: list[dict[str, Any]] = []
    queue = [_normalize_root(workspace_root)]

    while queue:
        current_dir = queue.pop(0)
        for entry in backend.ls_info(current_dir):
            entry_path = entry.get("path") if isinstance(entry, dict) else None
            if not isinstance(entry_path, str):
                continue

            normalized = posixpath.normpath(entry_path)
            if not normalized.startswith("/"):
                normalized = f"/{normalized}"

            if not _is_within_root(workspace_root, normalized):
                continue

            rel_path = _to_relative_path(workspace_root, normalized)
            if rel_path == "/" or _is_hidden_or_ignored(rel_path):
                continue

            is_dir = bool(entry.get("is_dir")) if isinstance(entry, dict) else False
            item: dict[str, Any] = {
                "path": rel_path,
                "is_dir": is_dir,
            }
            if isinstance(entry, dict):
                size = entry.get("size")
                modified_at = entry.get("modified_at")
                if isinstance(size, int):
                    item["size"] = size
                if isinstance(modified_at, str):
                    item["modified_at"] = modified_at
            files.append(item)

            if is_dir:
                queue.append(normalized)

    files.sort(key=lambda x: x.get("path", ""))
    return files


def _download_file_bytes(backend: Any, full_path: str) -> bytes:
    responses = backend.download_files([full_path])
    if not responses:
        raise HTTPException(status_code=404, detail="File not found")

    first = responses[0]
    error = getattr(first, "error", None)
    if error:
        if error in {"file_not_found", "invalid_path"}:
            raise HTTPException(status_code=404, detail="File not found")
        if error == "permission_denied":
            raise HTTPException(status_code=403, detail="Access denied")
        if error == "is_directory":
            raise HTTPException(status_code=400, detail="Cannot read directory")
        raise HTTPException(status_code=400, detail=str(error))

    content = getattr(first, "content", None)
    if content is None:
        raise HTTPException(status_code=404, detail="File not found")
    if not isinstance(content, (bytes, bytearray)):
        raise HTTPException(status_code=500, detail="Unexpected file content type")
    return bytes(content)


@router.get("")
def get_workspace(thread_id: str, user: User = Depends(get_current_user)):
    _get_owned_thread(thread_id, user)
    daytona_context = _get_daytona_context(thread_id)
    return {"path": _normalize_root(daytona_context.workspace_root)}


@router.get("/files", response_model=WorkspaceListOut)
def list_files(thread_id: str, user: User = Depends(get_current_user)):
    _get_owned_thread(thread_id, user)
    daytona_context = _get_daytona_context(thread_id)
    files = _list_workspace_files(daytona_context.backend, daytona_context.workspace_root)
    return {
        "success": True,
        "files": files,
        "workspacePath": _normalize_root(daytona_context.workspace_root),
    }


@router.get("/file", response_model=WorkspaceReadOut)
def read_file(thread_id: str, path: str, user: User = Depends(get_current_user)):
    _get_owned_thread(thread_id, user)
    daytona_context = _get_daytona_context(thread_id)

    full_path = _safe_sandbox_path(daytona_context.workspace_root, path)
    try:
        data = _download_file_bytes(daytona_context.backend, full_path)
        content = data.decode("utf-8")
    except HTTPException:
        raise
    except UnicodeDecodeError:
        return {"success": False, "error": "File is not valid UTF-8 text"}
    except Exception as e:
        return {"success": False, "error": str(e)}

    return {
        "success": True,
        "content": content,
        "size": len(data),
    }


@router.get("/file-binary", response_model=WorkspaceReadOut)
def read_file_binary(thread_id: str, path: str, user: User = Depends(get_current_user)):
    _get_owned_thread(thread_id, user)
    daytona_context = _get_daytona_context(thread_id)

    full_path = _safe_sandbox_path(daytona_context.workspace_root, path)
    try:
        data = _download_file_bytes(daytona_context.backend, full_path)
        content = base64.b64encode(data).decode("utf-8")
    except HTTPException:
        raise
    except Exception as e:
        return {"success": False, "error": str(e)}

    return {
        "success": True,
        "content": content,
        "size": len(data),
    }


@router.post("/sync")
def sync_to_disk(_payload: dict, _user: User = Depends(get_current_user)):
    # Deprecated: local disk sync is intentionally disabled for Daytona-only backend.
    return {
        "success": False,
        "written": 0,
        "errors": [{"path": "/", "error": "Local sync is disabled"}],
        "message": "Workspace files are stored in Daytona sandbox",
    }
