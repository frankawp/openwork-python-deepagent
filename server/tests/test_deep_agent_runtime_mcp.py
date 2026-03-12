from __future__ import annotations

import types
import unittest
from unittest.mock import patch

from langchain_core.tools import StructuredTool, ToolException

from app.deep_agent_runtime import _load_thread_mcp_tools


class _FakeDB:
    def close(self) -> None:
        return


class _FakeClient:
    def __init__(self, connections: dict[str, dict], tool_name_prefix: bool = False) -> None:
        self._server_key = next(iter(connections.keys()))

    async def get_tools(self, *, server_name: str | None = None):
        if self._server_key == "good":
            return [types.SimpleNamespace(name="good_tool")]
        raise RuntimeError(f"{self._server_key} is down")


class _ToolBehaviorClient:
    def __init__(self, connections: dict[str, dict], tool_name_prefix: bool = False) -> None:
        self._server_key = next(iter(connections.keys()))

    async def get_tools(self, *, server_name: str | None = None):
        if self._server_key != "good":
            raise RuntimeError(f"{self._server_key} is down")

        async def outside_read(path: str) -> str:
            raise ToolException(
                f"Access denied - path outside allowed directories: {path} not in /home/daytona"
            )

        async def list_dir(path: str) -> str:
            return f"list ok: {path}"

        return [
            StructuredTool.from_function(
                coroutine=outside_read,
                name="mcp-fs_read_text_file",
                description="read text file",
            ),
            StructuredTool.from_function(
                coroutine=list_dir,
                name="mcp-fs_list_directory",
                description="list directory",
            ),
        ]


class LoadThreadMcpToolsTests(unittest.IsolatedAsyncioTestCase):
    async def test_partial_failure_still_returns_working_tools(self) -> None:
        updates: list[tuple[str, str | None]] = []

        def _record_state(thread_id: str, *, status: str, last_error: str | None = None) -> None:
            updates.append((status, last_error))

        servers = [
            types.SimpleNamespace(key="good"),
            types.SimpleNamespace(key="bad"),
        ]

        def _build_entry(server, *, thread_id=None, daytona_sandbox=None):  # type: ignore[no-untyped-def]
            if server.key == "bad":
                raise RuntimeError("bad config")
            return {"transport": "streamable_http", "url": "http://localhost/mcp"}

        with (
            patch("app.deep_agent_runtime.SessionLocal", return_value=_FakeDB()),
            patch("app.deep_agent_runtime.get_runtime_thread_mcp_servers", return_value=servers),
            patch("app.deep_agent_runtime._get_mcp_cooldown_reason", return_value=None),
            patch("app.deep_agent_runtime.build_mcp_client_entry", side_effect=_build_entry),
            patch("app.deep_agent_runtime.MultiServerMCPClient", _FakeClient),
            patch("app.deep_agent_runtime._update_thread_mcp_state", side_effect=_record_state),
        ):
            result = await _load_thread_mcp_tools("thread-1", daytona_sandbox=object())

        self.assertEqual([tool.name for tool in result.tools], ["good_tool"])
        self.assertFalse(result.degraded)
        self.assertEqual(updates[0][0], "connecting")
        self.assertEqual(updates[-1][0], "ready")
        self.assertIn("bad: RuntimeError: bad config", updates[-1][1] or "")

    async def test_all_failures_degrade_without_raising(self) -> None:
        updates: list[tuple[str, str | None]] = []

        def _record_state(thread_id: str, *, status: str, last_error: str | None = None) -> None:
            updates.append((status, last_error))

        servers = [types.SimpleNamespace(key="bad")]

        with (
            patch("app.deep_agent_runtime.SessionLocal", return_value=_FakeDB()),
            patch("app.deep_agent_runtime.get_runtime_thread_mcp_servers", return_value=servers),
            patch("app.deep_agent_runtime._get_mcp_cooldown_reason", return_value=None),
            patch(
                "app.deep_agent_runtime.build_mcp_client_entry",
                side_effect=RuntimeError("bad config"),
            ),
            patch("app.deep_agent_runtime._update_thread_mcp_state", side_effect=_record_state),
        ):
            result = await _load_thread_mcp_tools("thread-1", daytona_sandbox=object())

        self.assertEqual(result.tools, [])
        self.assertTrue(result.degraded)
        self.assertIn("bad: RuntimeError: bad config", result.degraded_reason or "")
        self.assertEqual(updates[-1][0], "failed")
        self.assertIn("bad: RuntimeError: bad config", updates[-1][1] or "")

    async def test_tool_exception_is_returned_as_content_and_next_tool_still_runs(self) -> None:
        updates: list[tuple[str, str | None]] = []

        def _record_state(thread_id: str, *, status: str, last_error: str | None = None) -> None:
            updates.append((status, last_error))

        servers = [types.SimpleNamespace(key="good")]

        with (
            patch("app.deep_agent_runtime.SessionLocal", return_value=_FakeDB()),
            patch("app.deep_agent_runtime.get_runtime_thread_mcp_servers", return_value=servers),
            patch("app.deep_agent_runtime._get_mcp_cooldown_reason", return_value=None),
            patch(
                "app.deep_agent_runtime.build_mcp_client_entry",
                return_value={"transport": "streamable_http", "url": "http://localhost/mcp"},
            ),
            patch("app.deep_agent_runtime.MultiServerMCPClient", _ToolBehaviorClient),
            patch("app.deep_agent_runtime._update_thread_mcp_state", side_effect=_record_state),
        ):
            result = await _load_thread_mcp_tools("thread-1", daytona_sandbox=object())

        tools = result.tools

        by_name = {tool.name: tool for tool in tools}
        read_tool = by_name["mcp-fs_read_text_file"]
        list_tool = by_name["mcp-fs_list_directory"]

        self.assertTrue(read_tool.handle_tool_error)
        self.assertTrue(list_tool.handle_tool_error)

        denied = await read_tool.ainvoke({"path": "/Users/frankliu/.zshrc"})
        listed = await list_tool.ainvoke({"path": "/home/daytona"})

        self.assertIn("Access denied - path outside allowed directories", denied)
        self.assertEqual("list ok: /home/daytona", listed)
        self.assertFalse(result.degraded)
        self.assertEqual(updates[0][0], "connecting")
        self.assertEqual(updates[-1][0], "ready")

    async def test_recent_failure_cooldown_skips_mcp_reconnect(self) -> None:
        servers = [types.SimpleNamespace(key="good")]

        with (
            patch("app.deep_agent_runtime.SessionLocal", return_value=_FakeDB()),
            patch("app.deep_agent_runtime.get_runtime_thread_mcp_servers", return_value=servers),
            patch(
                "app.deep_agent_runtime._get_mcp_cooldown_reason",
                return_value="MCP reconnect cooldown active (60s remaining).",
            ),
            patch("app.deep_agent_runtime.build_mcp_client_entry") as build_entry,
            patch("app.deep_agent_runtime.MultiServerMCPClient") as mcp_client,
            patch("app.deep_agent_runtime._update_thread_mcp_state") as update_state,
        ):
            result = await _load_thread_mcp_tools("thread-1", daytona_sandbox=object())

        self.assertEqual(result.tools, [])
        self.assertTrue(result.degraded)
        self.assertIn("cooldown", (result.degraded_reason or "").lower())
        build_entry.assert_not_called()
        mcp_client.assert_not_called()
        update_state.assert_not_called()

    async def test_exception_group_is_summarized_into_degraded_reason(self) -> None:
        updates: list[tuple[str, str | None]] = []

        def _record_state(thread_id: str, *, status: str, last_error: str | None = None) -> None:
            updates.append((status, last_error))

        class _GroupedErrorClient:
            def __init__(self, connections: dict[str, dict], tool_name_prefix: bool = False) -> None:
                self._server_key = next(iter(connections.keys()))

            async def get_tools(self, *, server_name: str | None = None):
                raise ExceptionGroup(
                    "unhandled errors in a TaskGroup",
                    [
                        RuntimeError("connect timeout"),
                        ValueError("bad handshake"),
                    ],
                )

        servers = [types.SimpleNamespace(key="mcp-fs")]

        with (
            patch("app.deep_agent_runtime.SessionLocal", return_value=_FakeDB()),
            patch("app.deep_agent_runtime.get_runtime_thread_mcp_servers", return_value=servers),
            patch("app.deep_agent_runtime._get_mcp_cooldown_reason", return_value=None),
            patch(
                "app.deep_agent_runtime.build_mcp_client_entry",
                return_value={"transport": "streamable_http", "url": "http://localhost/mcp"},
            ),
            patch("app.deep_agent_runtime.MultiServerMCPClient", _GroupedErrorClient),
            patch("app.deep_agent_runtime._update_thread_mcp_state", side_effect=_record_state),
        ):
            result = await _load_thread_mcp_tools("thread-1", daytona_sandbox=object())

        self.assertEqual(result.tools, [])
        self.assertTrue(result.degraded)
        detail = result.degraded_reason or ""
        self.assertIn("RuntimeError: connect timeout", detail)
        self.assertIn("ValueError: bad handshake", detail)
        self.assertEqual(updates[-1][0], "failed")


if __name__ == "__main__":
    unittest.main()
