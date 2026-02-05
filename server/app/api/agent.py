from __future__ import annotations

import json
import uuid
from typing import AsyncGenerator

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from langchain_core.load.dump import dumpd
from langgraph.types import Command

from pathlib import Path

from ..config import load_config
from ..deep_agent_runtime import create_runtime
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


async def _agent_stream(
    payload: AgentStreamRequest, workspace_path: str, username: str
) -> AsyncGenerator[str, None]:
    msg_id = str(uuid.uuid4())
    try:
        agent = create_runtime(
            thread_id=payload.thread_id,
            workspace_path=workspace_path,
            username=username,
            model_id=payload.model_id,
            skills_enabled=payload.skills_enabled,
        )

        config = {"configurable": {"thread_id": payload.thread_id}}

        if payload.command and payload.command.get("resume") is not None:
            resume = _normalize_resume(payload.command.get("resume"))
            command = Command(resume=resume)
            stream = agent.astream(command, config, stream_mode=["messages", "values", "updates"])
        else:
            stream = agent.astream(
                {"messages": [{"role": "user", "content": payload.message}]},
                config,
                stream_mode=["messages", "values", "updates"],
            )

        async for chunk in _stream_sse(stream):
            yield chunk

        yield _serialize_sse({"type": "done"})
    except Exception as e:
        message = str(e) or repr(e)
        yield _serialize_sse({"type": "error", "error": message})


async def _agent_interrupt(
    payload: AgentInterruptRequest, workspace_path: str, username: str
) -> AsyncGenerator[str, None]:
    try:
        agent = create_runtime(
            thread_id=payload.thread_id,
            workspace_path=workspace_path,
            username=username,
            model_id=payload.model_id,
            skills_enabled=payload.skills_enabled,
        )
        config = {"configurable": {"thread_id": payload.thread_id}}
        resume = _normalize_resume(payload.decision)
        command = Command(resume=resume)
        stream = agent.astream(command, config, stream_mode=["messages", "values", "updates"])

        async for chunk in _stream_sse(stream):
            yield chunk

        yield _serialize_sse({"type": "done"})
    except Exception as e:
        message = str(e) or repr(e)
        yield _serialize_sse({"type": "error", "error": message})


@router.post("/stream")
def stream_agent(payload: AgentStreamRequest, _user: User = Depends(get_current_user)):
    cfg = load_config()
    workspace_path = str(Path(cfg.workspace.root) / _user.username)
    generator = _agent_stream(payload, workspace_path, _user.username)
    return StreamingResponse(generator, media_type="text/event-stream")


@router.post("/interrupt")
def interrupt_agent(payload: AgentInterruptRequest, _user: User = Depends(get_current_user)):
    cfg = load_config()
    workspace_path = str(Path(cfg.workspace.root) / _user.username)
    generator = _agent_interrupt(payload, workspace_path, _user.username)
    return StreamingResponse(generator, media_type="text/event-stream")
