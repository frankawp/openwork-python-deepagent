from __future__ import annotations

import json
from typing import AsyncGenerator

import httpx

from .crypto import decrypt
from .db import SessionLocal
from .model_catalog import DEFAULT_MODEL_ID, MODELS
from .models import AppSetting, GlobalApiKey


def _provider_for_model_id(model_id: str) -> str | None:
    model = next((m for m in MODELS if m.id == model_id), None)
    return model.provider if model else None


def get_default_model_id() -> str:
    db = SessionLocal()
    try:
        setting = db.get(AppSetting, "default_model")
        candidate = setting.value if setting else DEFAULT_MODEL_ID
        provider = _provider_for_model_id(candidate)
        if provider and get_api_key(provider):
            return candidate
        # fallback to deepseek if available
        if get_api_key("deepseek"):
            return "deepseek-chat"
        return candidate
    finally:
        db.close()


def resolve_model(model_id: str | None) -> tuple[str, str]:
    model_id = model_id or get_default_model_id()
    model = next((m for m in MODELS if m.id == model_id), None)
    if model:
        if get_api_key(model.provider):
            return model.provider, model.model
        if get_api_key("deepseek"):
            return "deepseek", "deepseek-chat"
        return model.provider, model.model

    # If not found, assume it's a direct model name under deepseek
    return "deepseek", model_id


def get_api_key(provider: str) -> str | None:
    db = SessionLocal()
    try:
        row = db.get(GlobalApiKey, provider)
        if not row:
            return None
        return decrypt(row.encrypted_key)
    finally:
        db.close()


async def stream_chat_completion(message: str, model_id: str | None) -> AsyncGenerator[str, None]:
    provider, model_name = resolve_model(model_id)
    if provider != "deepseek":
        raise RuntimeError(f"Provider {provider} not configured")

    api_key = get_api_key("deepseek")
    if not api_key:
        raise RuntimeError("DeepSeek API key not configured")

    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {
        "model": model_name,
        "messages": [{"role": "user", "content": message}],
        "stream": True,
    }

    async with httpx.AsyncClient(base_url="https://api.deepseek.com", timeout=60.0) as client:
        async with client.stream("POST", "/v1/chat/completions", headers=headers, json=payload) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if not line:
                    continue
                if line.startswith("data:"):
                    data = line[len("data:") :].strip()
                else:
                    data = line.strip()

                if data == "[DONE]":
                    break

                try:
                    chunk = json.loads(data)
                except json.JSONDecodeError:
                    continue

                delta = chunk.get("choices", [{}])[0].get("delta", {})
                token = delta.get("content")
                if token:
                    yield token
