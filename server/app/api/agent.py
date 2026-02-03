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
from ..schemas import AgentStreamRequest

router = APIRouter(prefix="/agent", tags=["agent"])


def _serialize_sse(payload: dict) -> str:
    return f"data: {json.dumps(payload)}\n\n"


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
            command = Command(resume=payload.command.get("resume"))
            stream = agent.astream(command, config, stream_mode=["messages", "values"])
        else:
            stream = agent.astream(
                {"messages": [{"role": "user", "content": payload.message}]},
                config,
                stream_mode=["messages", "values"],
            )

        async for mode, data in stream:
            if mode == "messages":
                # data is (message, metadata)
                payload_data = [dumpd(data[0]), data[1]]
                yield _serialize_sse({"type": "stream", "mode": "messages", "data": payload_data})
            else:
                yield _serialize_sse({"type": "stream", "mode": "values", "data": dumpd(data)})

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
