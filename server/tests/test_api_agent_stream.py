from __future__ import annotations

import asyncio
import json
import unittest
from unittest.mock import patch

from app.api.agent import (
    _ACTIVE_STREAM_TASKS,
    _ACTIVE_STREAM_TASKS_LOCK,
    _agent_stream,
    _register_active_stream_task,
    _unregister_active_stream_task,
    cancel_agent,
)
from app.deep_agent_runtime import RuntimeCreationResult
from app.schemas import AgentCancelRequest, AgentStreamRequest


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


class AgentStreamCancellationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        await self._reset_registry()

    async def asyncTearDown(self) -> None:
        await self._reset_registry()

    async def _reset_registry(self) -> None:
        async with _ACTIVE_STREAM_TASKS_LOCK:
            tasks = list(_ACTIVE_STREAM_TASKS.values())
            _ACTIVE_STREAM_TASKS.clear()
        for task in tasks:
            if not task.done():
                task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def test_cancel_endpoint_cancels_active_stream_and_cleans_registry(self) -> None:
        registered = asyncio.Event()
        cancelled = asyncio.Event()

        async def _runner() -> None:
            await _register_active_stream_task("thread-cancel")
            registered.set()
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                cancelled.set()
                raise
            finally:
                await _unregister_active_stream_task("thread-cancel")

        task = asyncio.create_task(_runner())
        await asyncio.wait_for(registered.wait(), timeout=1)

        result = await cancel_agent(
            AgentCancelRequest(thread_id="thread-cancel"),
            _user=object(),
        )
        self.assertEqual(result, {"success": True, "cancelled": True})

        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertTrue(cancelled.is_set())

        async with _ACTIVE_STREAM_TASKS_LOCK:
            self.assertNotIn("thread-cancel", _ACTIVE_STREAM_TASKS)

        second_result = await cancel_agent(
            AgentCancelRequest(thread_id="thread-cancel"),
            _user=object(),
        )
        self.assertEqual(second_result, {"success": True, "cancelled": False})

    async def test_registering_new_stream_cancels_existing_stream_for_same_thread(self) -> None:
        first_registered = asyncio.Event()
        second_registered = asyncio.Event()
        first_cancelled = asyncio.Event()
        second_cancelled = asyncio.Event()

        async def _runner(registered: asyncio.Event, cancelled: asyncio.Event) -> None:
            await _register_active_stream_task("thread-replace")
            registered.set()
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                cancelled.set()
                raise
            finally:
                await _unregister_active_stream_task("thread-replace")

        first_task = asyncio.create_task(_runner(first_registered, first_cancelled))
        await asyncio.wait_for(first_registered.wait(), timeout=1)

        second_task = asyncio.create_task(_runner(second_registered, second_cancelled))
        await asyncio.wait_for(second_registered.wait(), timeout=1)
        await asyncio.wait_for(first_cancelled.wait(), timeout=1)

        with self.assertRaises(asyncio.CancelledError):
            await first_task

        async with _ACTIVE_STREAM_TASKS_LOCK:
            self.assertIs(_ACTIVE_STREAM_TASKS.get("thread-replace"), second_task)

        second_task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await second_task
        self.assertTrue(second_cancelled.is_set())

        async with _ACTIVE_STREAM_TASKS_LOCK:
            self.assertNotIn("thread-replace", _ACTIVE_STREAM_TASKS)


if __name__ == "__main__":
    unittest.main()
