from __future__ import annotations

import json
from typing import AsyncGenerator

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from langchain_core.load.dump import dumpd
from langgraph.types import Command

from ..deep_agent_runtime import (
    DEEPSEEK_CHAT_MODEL_ID,
    create_runtime,
    should_fallback_to_deepseek_chat,
)
from ..deps import get_current_user
from ..models import User
from ..schemas import AgentInterruptRequest, AgentStreamRequest

router = APIRouter(prefix="/agent", tags=["agent"])


def _serialize_sse(payload: dict) -> str:
    return f"data: {json.dumps(payload)}\n\n"


def _normalize_interrupts(data: object) -> object:
    if not isinstance(data, dict):
        return data
    interrupts = data.get("__interrupt__")
    if not isinstance(interrupts, (list, tuple)):
        return data

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

    return {**data, "__interrupt__": normalized}


def _normalize_resume(resume: object) -> object:
    if not isinstance(resume, dict):
        return resume
    if "decisions" in resume:
        return resume
    decision = resume.get("decision") or resume.get("type")
    if not decision:
        return resume

    decision_item: dict[str, object] = {"type": decision}
    if "tool_call_id" in resume:
        decision_item["tool_call_id"] = resume.get("tool_call_id")
    if "edited_args" in resume:
        decision_item["edited_args"] = resume.get("edited_args")
    if "feedback" in resume:
        decision_item["feedback"] = resume.get("feedback")

    return {"decisions": [decision_item]}


async def _stream_sse(stream) -> AsyncGenerator[str, None]:
    async for mode, data in stream:
        if mode == "messages":
            payload_data = [dumpd(data[0]), data[1]]
            yield _serialize_sse({"type": "stream", "mode": "messages", "data": payload_data})
        elif mode == "values":
            yield _serialize_sse(
                {
                    "type": "stream",
                    "mode": "values",
                    "data": dumpd(_normalize_interrupts(data)),
                }
            )
        elif mode == "updates":
            yield _serialize_sse(
                {
                    "type": "stream",
                    "mode": "values",
                    "data": dumpd(_normalize_interrupts(data)),
                }
            )


async def _agent_stream(payload: AgentStreamRequest) -> AsyncGenerator[str, None]:
    model_candidates = [payload.model_id]
    if should_fallback_to_deepseek_chat(payload.model_id):
        model_candidates.append(DEEPSEEK_CHAT_MODEL_ID)

    last_error: Exception | None = None
    for index, model_id in enumerate(model_candidates):
        emitted_any = False
        try:
            agent = create_runtime(
                thread_id=payload.thread_id,
                model_id=model_id,
            )

            config = {"configurable": {"thread_id": payload.thread_id}}

            if payload.command and payload.command.get("resume") is not None:
                resume = _normalize_resume(payload.command.get("resume"))
                command = Command(resume=resume)
                stream = agent.astream(
                    command,
                    config,
                    stream_mode=["messages", "values", "updates"],
                )
            else:
                stream = agent.astream(
                    {"messages": [{"role": "user", "content": payload.message}]},
                    config,
                    stream_mode=["messages", "values", "updates"],
                )

            async for chunk in _stream_sse(stream):
                emitted_any = True
                yield chunk

            yield _serialize_sse({"type": "done"})
            return
        except Exception as e:
            last_error = e
            is_primary_attempt = index == 0
            has_fallback = len(model_candidates) > 1
            if is_primary_attempt and has_fallback and not emitted_any:
                continue
            message = str(last_error) or repr(last_error)
            yield _serialize_sse({"type": "error", "error": message})
            return


async def _agent_interrupt(payload: AgentInterruptRequest) -> AsyncGenerator[str, None]:
    model_candidates = [payload.model_id]
    if should_fallback_to_deepseek_chat(payload.model_id):
        model_candidates.append(DEEPSEEK_CHAT_MODEL_ID)

    last_error: Exception | None = None
    for index, model_id in enumerate(model_candidates):
        emitted_any = False
        try:
            agent = create_runtime(
                thread_id=payload.thread_id,
                model_id=model_id,
            )
            config = {"configurable": {"thread_id": payload.thread_id}}
            resume = _normalize_resume(payload.decision)
            command = Command(resume=resume)
            stream = agent.astream(
                command,
                config,
                stream_mode=["messages", "values", "updates"],
            )

            async for chunk in _stream_sse(stream):
                emitted_any = True
                yield chunk

            yield _serialize_sse({"type": "done"})
            return
        except Exception as e:
            last_error = e
            is_primary_attempt = index == 0
            has_fallback = len(model_candidates) > 1
            if is_primary_attempt and has_fallback and not emitted_any:
                continue
            message = str(last_error) or repr(last_error)
            yield _serialize_sse({"type": "error", "error": message})
            return


@router.post("/stream")
def stream_agent(payload: AgentStreamRequest, _user: User = Depends(get_current_user)):
    generator = _agent_stream(payload)
    return StreamingResponse(generator, media_type="text/event-stream")


@router.post("/interrupt")
def interrupt_agent(payload: AgentInterruptRequest, _user: User = Depends(get_current_user)):
    generator = _agent_interrupt(payload)
    return StreamingResponse(generator, media_type="text/event-stream")
