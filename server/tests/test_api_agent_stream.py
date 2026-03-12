from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from app.api.agent import _agent_stream
from app.deep_agent_runtime import RuntimeCreationResult
from app.schemas import AgentStreamRequest


class _FakeAgent:
    def astream(self, *_args, **_kwargs):  # type: ignore[no-untyped-def]
        async def _empty_stream():
            if False:
                yield None

        return _empty_stream()


async def _collect_sse_payloads(payload: AgentStreamRequest) -> list[dict]:
    events: list[dict] = []
    async for chunk in _agent_stream(payload):
        assert chunk.startswith("data: ")
        events.append(json.loads(chunk[len("data: ") :].strip()))
    return events


class AgentStreamMCPWarningTests(unittest.IsolatedAsyncioTestCase):
    async def test_emits_warning_and_continues_when_runtime_is_mcp_degraded(self) -> None:
        payload = AgentStreamRequest(
            thread_id="thread-1",
            message="hello",
        )

        async def _fake_create_runtime(**_kwargs):  # type: ignore[no-untyped-def]
            return RuntimeCreationResult(
                agent=_FakeAgent(),
                mcp_degraded=True,
                mcp_degraded_reason="MCP reconnect cooldown active (80s remaining).",
            )

        with (
            patch("app.api.agent.should_fallback_to_deepseek_chat", return_value=False),
            patch("app.api.agent.create_runtime", side_effect=_fake_create_runtime),
        ):
            events = await _collect_sse_payloads(payload)

        self.assertEqual(events[0]["type"], "warning")
        self.assertEqual(events[0]["warning_type"], "mcp_degraded")
        self.assertIn("Continuing without MCP tools", events[0]["message"])
        self.assertIn("cooldown", events[0]["reason"].lower())
        self.assertEqual(events[-1]["type"], "done")
        self.assertFalse(any(event.get("type") == "error" for event in events))

    async def test_does_not_emit_warning_when_runtime_has_full_mcp(self) -> None:
        payload = AgentStreamRequest(
            thread_id="thread-1",
            message="hello",
        )

        async def _fake_create_runtime(**_kwargs):  # type: ignore[no-untyped-def]
            return RuntimeCreationResult(
                agent=_FakeAgent(),
                mcp_degraded=False,
                mcp_degraded_reason=None,
            )

        with (
            patch("app.api.agent.should_fallback_to_deepseek_chat", return_value=False),
            patch("app.api.agent.create_runtime", side_effect=_fake_create_runtime),
        ):
            events = await _collect_sse_payloads(payload)

        self.assertEqual(events[-1]["type"], "done")
        self.assertFalse(any(event.get("type") == "warning" for event in events))


if __name__ == "__main__":
    unittest.main()
