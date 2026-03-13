from __future__ import annotations

import asyncio
import datetime as dt

from fastapi import APIRouter, Depends, HTTPException
from langchain_mcp_adapters.client import MultiServerMCPClient
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..checkpointer_mysql import MySQLSaver
from ..config import load_config
from ..daytona_backend import get_or_create_daytona_backend
from ..deps import get_current_user, get_db
from ..mcp_service import (
    build_mcp_client_entry,
    ensure_mcp_owned,
    normalize_mcp_key,
    normalize_mcp_payload,
    serialize_secret,
    sync_user_mcp_bindings,
)
from ..models import MCPServer, Thread, User
from ..schemas import (
    MCPServerCreate,
    MCPServerOut,
    MCPServerTestIn,
    MCPServerTestOut,
    MCPServerUpdate,
)

router = APIRouter(prefix="/mcps", tags=["mcps"])
MCP_TEST_CONNECT_TIMEOUT_SECONDS = 20


def _clear_mcp_tools_cache(thread_ids: list[str]) -> None:
    if not thread_ids:
        return
    checkpointer = MySQLSaver()
    for thread_id in sorted(set(thread_ids)):
        checkpointer.clear_channel_value(thread_id, "mcp_tools_metadata")


def _to_mcp_out(server: MCPServer) -> MCPServerOut:
    return MCPServerOut(
        id=server.id,
        user_id=server.user_id,
        key=server.key,
        name=server.name,
        description=server.description,
        transport=server.transport,  # type: ignore[arg-type]
        config=server.config_json if isinstance(server.config_json, dict) else {},
        has_secret=bool(server.encrypted_secret_json),
        enabled=server.enabled,
        created_at=server.created_at,
        updated_at=server.updated_at,
    )


def _must_get_user_mcp(db: Session, mcp_id: str, user_id: str) -> MCPServer:
    try:
        return ensure_mcp_owned(db, mcp_id=mcp_id, user_id=user_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


def _clean_required_text(value: str, *, field: str) -> str:
    cleaned = (value or "").strip()
    if not cleaned:
        raise HTTPException(status_code=400, detail=f"{field} is required")
    return cleaned


@router.get("", response_model=list[MCPServerOut])
def list_mcps(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    servers = (
        db.query(MCPServer)
        .filter(MCPServer.user_id == user.id)
        .order_by(MCPServer.updated_at.desc())
        .all()
    )
    return [_to_mcp_out(server) for server in servers]


@router.post("", response_model=MCPServerOut)
def create_mcp(
    payload: MCPServerCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        key = normalize_mcp_key(payload.key)
        config, secret = normalize_mcp_payload(
            transport=payload.transport,
            config=payload.config,
            secret=payload.secret,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    now = dt.datetime.utcnow()
    server = MCPServer(
        user_id=user.id,
        key=key,
        name=_clean_required_text(payload.name, field="name"),
        description=_clean_required_text(payload.description, field="description"),
        transport=payload.transport,
        config_json=config,
        encrypted_secret_json=serialize_secret(secret),
        enabled=payload.enabled,
        created_at=now,
        updated_at=now,
    )
    db.add(server)
    affected_thread_ids: list[str] = []
    try:
        db.flush()
        affected_thread_ids = sync_user_mcp_bindings(db, user_id=user.id)
        db.commit()
    except IntegrityError as e:
        db.rollback()
        raise HTTPException(status_code=409, detail="MCP key already exists") from e
    db.refresh(server)
    _clear_mcp_tools_cache(affected_thread_ids)
    return _to_mcp_out(server)


@router.get("/{mcp_id}", response_model=MCPServerOut)
def get_mcp(
    mcp_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    server = _must_get_user_mcp(db, mcp_id, user.id)
    return _to_mcp_out(server)


@router.patch("/{mcp_id}", response_model=MCPServerOut)
def update_mcp(
    mcp_id: str,
    payload: MCPServerUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    server = _must_get_user_mcp(db, mcp_id, user.id)
    changed = False
    runtime_changed = False

    if payload.name is not None:
        next_name = _clean_required_text(payload.name, field="name")
        if server.name != next_name:
            server.name = next_name
            changed = True
    if payload.description is not None:
        next_description = _clean_required_text(payload.description, field="description")
        if server.description != next_description:
            server.description = next_description
            changed = True

    transport = payload.transport if payload.transport is not None else server.transport
    next_config = payload.config if payload.config is not None else server.config_json
    secret_was_provided = "secret" in payload.model_fields_set
    current_secret_token = server.encrypted_secret_json
    next_secret_payload = None if not secret_was_provided else payload.secret

    transport_or_config_changed = payload.transport is not None or payload.config is not None
    if transport_or_config_changed or secret_was_provided:
        try:
            config, normalized_secret = normalize_mcp_payload(
                transport=transport,
                config=next_config if isinstance(next_config, dict) else None,
                secret=next_secret_payload,
            )
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e

        next_secret_token = (
            serialize_secret(normalized_secret)
            if secret_was_provided
            else current_secret_token
        )
        if server.transport != transport:
            server.transport = transport
            changed = True
            runtime_changed = True
        if server.config_json != config:
            server.config_json = config
            changed = True
            runtime_changed = True
        if server.encrypted_secret_json != next_secret_token:
            server.encrypted_secret_json = next_secret_token
            changed = True
            runtime_changed = True

    if payload.enabled is not None and server.enabled != payload.enabled:
        server.enabled = payload.enabled
        changed = True
        runtime_changed = True

    if changed:
        server.updated_at = dt.datetime.utcnow()
        affected_thread_ids: list[str] = []
        if runtime_changed:
            affected_thread_ids = sync_user_mcp_bindings(db, user_id=user.id)
        try:
            db.commit()
        except IntegrityError as e:
            db.rollback()
            raise HTTPException(status_code=409, detail="MCP key already exists") from e
        if runtime_changed:
            _clear_mcp_tools_cache(affected_thread_ids)
        db.refresh(server)
    return _to_mcp_out(server)


@router.delete("/{mcp_id}")
def delete_mcp(
    mcp_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    server = _must_get_user_mcp(db, mcp_id, user.id)
    db.delete(server)
    db.flush()
    affected_thread_ids = sync_user_mcp_bindings(db, user_id=user.id)
    db.commit()
    _clear_mcp_tools_cache(affected_thread_ids)
    return {"success": True}


@router.post("/{mcp_id}/test", response_model=MCPServerTestOut)
async def test_mcp_connection(
    mcp_id: str,
    payload: MCPServerTestIn | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    server = _must_get_user_mcp(db, mcp_id, user.id)
    requested_thread_id = ((payload.thread_id or "").strip() if payload else "")
    selected_thread: Thread | None = None
    if requested_thread_id:
        selected_thread = db.get(Thread, requested_thread_id)
        if not selected_thread or selected_thread.user_id != user.id:
            return MCPServerTestOut(
                success=False,
                message=f"Session {requested_thread_id} was not found for current user.",
                tool_count=0,
                tools=[],
            )
    else:
        selected_thread = (
            db.query(Thread)
            .filter(Thread.user_id == user.id)
            .order_by(Thread.updated_at.desc())
            .first()
        )
    if not selected_thread:
        return MCPServerTestOut(
            success=False,
            message="No active session found. Please create or open a session, then retry Test Connect.",
            tool_count=0,
            tools=[],
        )

    cfg = load_config()
    try:
        daytona_context = get_or_create_daytona_backend(
            thread_id=selected_thread.id,
            command_timeout_seconds=cfg.sandbox.time_limit_sec,
            allow_create_if_missing=False,
        )
    except Exception as e:
        return MCPServerTestOut(
            success=False,
            message=f"Sandbox unavailable for session {selected_thread.id}: {e}",
            tool_count=0,
            tools=[],
        )

    try:
        entry = build_mcp_client_entry(
            server,
            thread_id=selected_thread.id,
            daytona_sandbox=daytona_context.sandbox,
        )
        client = MultiServerMCPClient({server.key: entry}, tool_name_prefix=True)
        tools = await asyncio.wait_for(
            client.get_tools(server_name=server.key),
            timeout=MCP_TEST_CONNECT_TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError:
        return MCPServerTestOut(
            success=False,
            message=(
                "MCP test timed out while discovering tools "
                f"(>{MCP_TEST_CONNECT_TIMEOUT_SECONDS}s) via sandbox thread {selected_thread.id}. "
                "Please verify the MCP command/package is valid and reachable in the sandbox."
            ),
            tool_count=0,
            tools=[],
        )
    except Exception as e:
        return MCPServerTestOut(
            success=False,
            message=f"{str(e) or repr(e)} (via sandbox thread {selected_thread.id})",
            tool_count=0,
            tools=[],
        )

    tool_names = sorted({getattr(tool, "name", "unknown") for tool in tools if tool})
    return MCPServerTestOut(
        success=True,
        message=f"MCP connection succeeded via sandbox thread {selected_thread.id}",
        tool_count=len(tool_names),
        tools=tool_names[:50],
    )
