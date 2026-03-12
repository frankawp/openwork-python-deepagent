from __future__ import annotations

import types
import unittest
from unittest.mock import patch

from app.mcp_service import build_mcp_client_entry


class _FakeProcess:
    def __init__(self) -> None:
        self.last_command = ""
        self.last_timeout: int | None = None

    def exec(self, command: str, timeout: int | None = None) -> types.SimpleNamespace:
        self.last_command = command
        self.last_timeout = timeout
        return types.SimpleNamespace(exit_code=0, result="")


class _FakeSandbox:
    def __init__(self) -> None:
        self.process = _FakeProcess()
        self.preview_calls: list[tuple[int, int | None]] = []

    def create_signed_preview_url(
        self,
        port: int,
        expires_in_seconds: int | None = None,
    ) -> types.SimpleNamespace:
        self.preview_calls.append((port, expires_in_seconds))
        return types.SimpleNamespace(url=f"https://preview.daytona.test/{port}")


def _server(
    *,
    key: str = "mcp-fs",
    transport: str = "stdio",
    command: str = "npx",
    args: list[str] | None = None,
) -> types.SimpleNamespace:
    return types.SimpleNamespace(
        key=key,
        transport=transport,
        config_json={"command": command, "args": args or []},
        encrypted_secret_json=None,
    )


class McpServiceRuntimeConfigTests(unittest.TestCase):
    def test_stdio_uses_host_process_without_daytona_context(self) -> None:
        server = _server(args=["-y", "@modelcontextprotocol/server-filesystem", "/tmp"])
        entry = build_mcp_client_entry(server)
        self.assertEqual(
            entry,
            {
                "transport": "stdio",
                "command": "npx",
                "args": ["-y", "@modelcontextprotocol/server-filesystem", "/tmp"],
            },
        )

    def test_stdio_uses_daytona_proxy_with_thread_context(self) -> None:
        sandbox = _FakeSandbox()
        server = _server(args=["-y", "@modelcontextprotocol/server-filesystem", "/home/daytona"])
        with patch("app.mcp_service._wait_for_daytona_bridge_ready", return_value=None):
            entry = build_mcp_client_entry(
                server,
                thread_id="thread-123",
                daytona_sandbox=sandbox,
            )

        self.assertEqual(entry["transport"], "streamable_http")
        self.assertTrue(entry["url"].endswith("/mcp"))
        self.assertIn("supergateway", sandbox.process.last_command)
        self.assertIn("@modelcontextprotocol/server-filesystem", sandbox.process.last_command)
        self.assertIn("/home/daytona", sandbox.process.last_command)
        self.assertGreaterEqual(len(sandbox.preview_calls), 1)


if __name__ == "__main__":
    unittest.main()
