from __future__ import annotations

import asyncio
import datetime as dt
from dataclasses import dataclass
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import SystemMessage
from langchain_mcp_adapters.client import MultiServerMCPClient

from deepagents import create_deep_agent

from .config import load_config
from .checkpointer_mysql import MySQLSaver
from .crypto import decrypt
from .db import SessionLocal
from .daytona_backend import (
    ensure_daytona_configured,
    get_or_create_daytona_backend,
)
from .model_catalog import DEFAULT_MODEL_ID, MODELS
from .models import AppSetting, GlobalApiKey, ThreadMCPRuntimeState
from .mcp_service import (
    STATUS_CONNECTING,
    STATUS_FAILED,
    STATUS_READY,
    build_mcp_client_entry,
    get_runtime_thread_mcp_servers,
    update_thread_mcp_runtime_state,
)
from .skills_service import get_runtime_skill_paths
from .system_prompt import build_system_prompt

DEEPSEEK_CHAT_MODEL_ID = "deepseek-chat"
DEEPSEEK_REASONER_MODEL_ID = "deepseek-reasoner"
MCP_TOOL_LOAD_TIMEOUT_SECONDS = 20
MCP_FAILURE_COOLDOWN_SECONDS = 120


@dataclass(frozen=True)
class MCPToolsLoadResult:
    tools: list[Any]
    degraded: bool
    degraded_reason: str | None = None


@dataclass(frozen=True)
class RuntimeCreationResult:
    agent: Any
    mcp_degraded: bool
    mcp_degraded_reason: str | None = None


def _get_api_key(provider: str) -> str | None:
    db = SessionLocal()
    try:
        row = db.get(GlobalApiKey, provider)
        if not row:
            return None
        return decrypt(row.encrypted_key)
    finally:
        db.close()


def _get_default_model_id() -> str:
    db = SessionLocal()
    try:
        setting = db.get(AppSetting, "default_model")
        return setting.value if setting else DEFAULT_MODEL_ID
    finally:
        db.close()


def _resolve_model(model_id: str | None) -> tuple[str, str]:
    model_id = model_id or _get_default_model_id()
    model = next((m for m in MODELS if m.id == model_id), None)
    if model:
        return model.provider, model.model
    return "deepseek", model_id


def resolve_runtime_model(model_id: str | None) -> tuple[str, str]:
    provider, model_name = _resolve_model(model_id)

    if provider != "deepseek" and not _get_api_key(provider) and _get_api_key("deepseek"):
        provider = "deepseek"
        model_name = DEEPSEEK_CHAT_MODEL_ID

    return provider, model_name


def should_fallback_to_deepseek_chat(model_id: str | None) -> bool:
    provider, model_name = resolve_runtime_model(model_id)
    return provider == "deepseek" and model_name == DEEPSEEK_REASONER_MODEL_ID


def _get_model_instance(model_id: str | None) -> BaseChatModel:
    provider, model_name = resolve_runtime_model(model_id)

    if provider == "deepseek":
        api_key = _get_api_key("deepseek")
        if not api_key:
            raise RuntimeError("DeepSeek API key not configured")
        try:
            from langchain_deepseek import ChatDeepSeek
        except Exception as e:
            raise RuntimeError(
                "langchain-deepseek is required for DeepSeek. Install it in the server venv."
            ) from e
        return ChatDeepSeek(
            model=model_name,
            api_key=api_key,
        )

    if provider == "openai":
        api_key = _get_api_key("openai")
        if not api_key:
            raise RuntimeError("OpenAI API key not configured")
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(model=model_name, api_key=api_key)

    if provider == "anthropic":
        api_key = _get_api_key("anthropic")
        if not api_key:
            raise RuntimeError("Anthropic API key not configured")
        from langchain_anthropic import ChatAnthropic

        return ChatAnthropic(model_name=model_name, api_key=api_key)

    if provider == "google":
        api_key = _get_api_key("google")
        if not api_key:
            raise RuntimeError("Google API key not configured")
        from langchain_google_genai import ChatGoogleGenerativeAI

        return ChatGoogleGenerativeAI(model=model_name, api_key=api_key)

    raise RuntimeError(f"Unsupported provider: {provider}")


def _update_thread_mcp_state(
    thread_id: str,
    *,
    status: str,
    last_error: str | None = None,
) -> None:
    db = SessionLocal()
    try:
        update_thread_mcp_runtime_state(
            db,
            thread_id=thread_id,
            status=status,
            last_error=last_error,
        )
        db.commit()
    finally:
        db.close()


def _configure_mcp_tools_for_runtime(tools: list[Any]) -> list[Any]:
    for tool in tools:
        if hasattr(tool, "handle_tool_error"):
            try:
                setattr(tool, "handle_tool_error", True)
            except Exception:
                pass
    return tools


def _collect_exception_messages(exc: BaseException) -> list[str]:
    if isinstance(exc, BaseExceptionGroup):
        messages: list[str] = []
        for sub_exc in exc.exceptions:
            messages.extend(_collect_exception_messages(sub_exc))
        return messages

    message = str(exc).strip()
    if not message:
        return [exc.__class__.__name__]
    if message.startswith(exc.__class__.__name__):
        return [message]
    return [f"{exc.__class__.__name__}: {message}"]


def _summarize_exception(exc: BaseException, *, max_items: int = 3) -> str:
    unique: list[str] = []
    for message in _collect_exception_messages(exc):
        if message not in unique:
            unique.append(message)
    summary = " | ".join(unique[:max_items]).strip()
    return summary or exc.__class__.__name__


def _format_mcp_error(server_key: str, exc: BaseException) -> str:
    return f"{server_key}: {_summarize_exception(exc)}"


def _get_mcp_cooldown_reason(thread_id: str) -> str | None:
    db = SessionLocal()
    try:
        state = db.get(ThreadMCPRuntimeState, thread_id)
    finally:
        db.close()

    if not state or state.status != STATUS_FAILED or not state.updated_at:
        return None

    elapsed = (dt.datetime.utcnow() - state.updated_at).total_seconds()
    remaining = int(MCP_FAILURE_COOLDOWN_SECONDS - elapsed)
    if remaining <= 0:
        return None

    last_error = (state.last_error or "MCP initialization failed previously").strip()
    return (
        f"MCP reconnect cooldown active ({remaining}s remaining). "
        f"Continuing without MCP tools. Last error: {last_error}"
    )[:4000]


async def _load_thread_mcp_tools(thread_id: str, *, daytona_sandbox: Any) -> MCPToolsLoadResult:
    db = SessionLocal()
    try:
        servers = get_runtime_thread_mcp_servers(db, thread_id=thread_id)
    finally:
        db.close()

    if not servers:
        _update_thread_mcp_state(thread_id, status=STATUS_READY, last_error=None)
        return MCPToolsLoadResult(tools=[], degraded=False, degraded_reason=None)

    cooldown_reason = _get_mcp_cooldown_reason(thread_id)
    if cooldown_reason:
        return MCPToolsLoadResult(tools=[], degraded=True, degraded_reason=cooldown_reason)

    mcp_configs: dict[str, dict[str, Any]] = {}
    errors: list[str] = []
    for server in servers:
        try:
            mcp_configs[server.key] = build_mcp_client_entry(
                server,
                thread_id=thread_id,
                daytona_sandbox=daytona_sandbox,
            )
        except Exception as e:
            errors.append(_format_mcp_error(server.key, e))

    if not mcp_configs:
        detail = "; ".join(errors)[:4000] if errors else None
        _update_thread_mcp_state(thread_id, status=STATUS_FAILED, last_error=detail)
        return MCPToolsLoadResult(tools=[], degraded=True, degraded_reason=detail)

    _update_thread_mcp_state(thread_id, status=STATUS_CONNECTING, last_error=None)
    all_tools: list[Any] = []
    for server_key, connection in mcp_configs.items():
        client = MultiServerMCPClient({server_key: connection}, tool_name_prefix=True)
        try:
            tools = await asyncio.wait_for(
                client.get_tools(server_name=server_key),
                timeout=MCP_TOOL_LOAD_TIMEOUT_SECONDS,
            )
            all_tools.extend(_configure_mcp_tools_for_runtime(tools))
        except Exception as e:
            errors.append(_format_mcp_error(server_key, e))

    if not all_tools and errors:
        detail = "; ".join(errors)[:4000]
        _update_thread_mcp_state(thread_id, status=STATUS_FAILED, last_error=detail)
        return MCPToolsLoadResult(tools=[], degraded=True, degraded_reason=detail)

    detail = "; ".join(errors)[:4000] if errors else None
    _update_thread_mcp_state(thread_id, status=STATUS_READY, last_error=detail)
    return MCPToolsLoadResult(tools=all_tools, degraded=False, degraded_reason=None)


async def create_runtime(
    thread_id: str,
    model_id: str | None = None,
    skills_enabled: bool = True,
) -> RuntimeCreationResult:
    model = _get_model_instance(model_id)
    checkpointer = MySQLSaver()
    cfg = load_config()

    ensure_daytona_configured()
    daytona_context = get_or_create_daytona_backend(
        thread_id=thread_id,
        command_timeout_seconds=cfg.sandbox.time_limit_sec,
        allow_create_if_missing=False,
    )
    backend = daytona_context.backend

    db = SessionLocal()
    try:
        skills_paths = get_runtime_skill_paths(
            db,
            thread_id=thread_id,
            skills_enabled=skills_enabled,
        )
    finally:
        db.close()
    mcp_result = await _load_thread_mcp_tools(
        thread_id,
        daytona_sandbox=daytona_context.sandbox,
    )

    system_prompt = build_system_prompt(daytona_context.workspace_root)

    agent = create_deep_agent(
        model=model,
        tools=mcp_result.tools,
        skills=skills_paths,
        system_prompt=SystemMessage(content=system_prompt),
        backend=backend,
        checkpointer=checkpointer,
        interrupt_on={"execute": True},
    )
    return RuntimeCreationResult(
        agent=agent,
        mcp_degraded=mcp_result.degraded,
        mcp_degraded_reason=mcp_result.degraded_reason,
    )
