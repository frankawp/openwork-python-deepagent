from __future__ import annotations

from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import SystemMessage

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
from .models import AppSetting, GlobalApiKey
from .system_prompt import build_system_prompt

DEEPSEEK_CHAT_MODEL_ID = "deepseek-chat"
DEEPSEEK_REASONER_MODEL_ID = "deepseek-reasoner"


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


def create_runtime(
    thread_id: str,
    model_id: str | None = None,
) -> Any:
    model = _get_model_instance(model_id)
    checkpointer = MySQLSaver()
    cfg = load_config()

    ensure_daytona_configured()
    daytona_context = get_or_create_daytona_backend(
        thread_id=thread_id,
        command_timeout_seconds=cfg.sandbox.time_limit_sec,
    )
    backend = daytona_context.backend

    skills_paths: list[str] = []
    system_prompt = build_system_prompt(daytona_context.workspace_root)

    agent = create_deep_agent(
        model=model,
        tools=[],
        skills=skills_paths,
        system_prompt=SystemMessage(content=system_prompt),
        backend=backend,
        checkpointer=checkpointer,
        interrupt_on={"execute": True},
    )
    return agent
