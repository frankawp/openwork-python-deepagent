from __future__ import annotations

from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import SystemMessage

from deepagents import create_deep_agent
from deepagents.backends import FilesystemBackend

from .agent_tools import make_execute_tool
from .analysis_env import ensure_analysis_environment
from .config import load_config
from .checkpointer_mysql import MySQLSaver
from .crypto import decrypt
from .db import SessionLocal
from .model_catalog import DEFAULT_MODEL_ID, MODELS
from .models import AppSetting, GlobalApiKey
from .sandbox.nsjail_sandbox import NsjailSandbox
from .skills import get_workspace_skills_path, init_workspace_skills
from .system_prompt import build_system_prompt


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


def _get_model_instance(model_id: str | None) -> BaseChatModel:
    provider, model_name = _resolve_model(model_id)

    if provider != "deepseek" and not _get_api_key(provider) and _get_api_key("deepseek"):
        provider = "deepseek"
        model_name = "deepseek-chat"

    if provider == "deepseek":
        api_key = _get_api_key("deepseek")
        if not api_key:
            raise RuntimeError("DeepSeek API key not configured")
        try:
            from langchain_openai import ChatOpenAI
        except Exception as e:
            raise RuntimeError(
                "langchain-openai is required for DeepSeek. Install it in the server venv."
            ) from e
        return ChatOpenAI(
            model=model_name,
            api_key=api_key,
            base_url="https://api.deepseek.com",
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


def create_runtime(
    thread_id: str,
    workspace_path: str,
    username: str,
    model_id: str | None = None,
    skills_enabled: bool = True,
) -> Any:
    model = _get_model_instance(model_id)
    checkpointer = MySQLSaver()
    backend = FilesystemBackend(root_dir=workspace_path, virtual_mode=True)
    cfg = load_config()

    if cfg.sandbox.enabled:
        sandbox = NsjailSandbox(workspace_path, cfg.sandbox)
    else:
        raise RuntimeError("Sandbox is required but disabled in config")

    ensure_analysis_environment(
        workspace_path,
        sandbox,
        timeout_seconds=cfg.sandbox.time_limit_sec,
        max_output_bytes=cfg.sandbox.max_output_bytes,
    )

    init_workspace_skills(workspace_path)

    # 构建 skills 路径（用户级别）
    skills_paths: list[str] = []
    if skills_enabled:
        skills_path = get_workspace_skills_path(workspace_path)
        if skills_path:
            skills_paths.append(str(skills_path))

    system_prompt = build_system_prompt(workspace_path)
    execute_tool = make_execute_tool(
        workspace_path,
        sandbox,
        timeout_seconds=cfg.sandbox.time_limit_sec,
        max_output_bytes=cfg.sandbox.max_output_bytes,
    )

    agent = create_deep_agent(
        model=model,
        tools=[execute_tool],
        skills=skills_paths,
        system_prompt=SystemMessage(content=system_prompt),
        backend=backend,
        checkpointer=checkpointer,
        interrupt_on={"execute": True},
    )
    return agent
