from __future__ import annotations

import asyncio
import datetime as dt
import types
import unittest
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.db import Base
from app.api.mcps import MCP_TEST_CONNECT_TIMEOUT_SECONDS, test_mcp_connection
from app.models import Thread, User
from app.schemas import MCPServerTestIn


class _FakeMCPClient:
    def __init__(self, connections: dict[str, dict], tool_name_prefix: bool = False) -> None:
        self._connections = connections
        self._tool_name_prefix = tool_name_prefix

    async def get_tools(self, *, server_name: str | None = None):
        return [types.SimpleNamespace(name="mcp-fs_list_directory")]


class McpTestConnectSandboxTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite+pysqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine, autoflush=False, autocommit=False)
        self.db: Session = self.Session()

    def tearDown(self) -> None:
        self.db.close()
        self.engine.dispose()

    def _create_user(self) -> User:
        now = dt.datetime.utcnow()
        user = User(
            username="tester",
            email="tester@example.com",
            password_hash="x",
            is_admin=False,
            created_at=now,
            updated_at=now,
        )
        self.db.add(user)
        self.db.commit()
        self.db.refresh(user)
        return user

    def _create_thread(self, *, user_id: str, updated_at: dt.datetime) -> Thread:
        thread = Thread(
            user_id=user_id,
            status="idle",
            title="thread",
            metadata_json={},
            thread_values={},
            created_at=updated_at,
            updated_at=updated_at,
        )
        self.db.add(thread)
        self.db.commit()
        self.db.refresh(thread)
        return thread

    async def test_uses_latest_updated_thread_for_sandbox_context(self) -> None:
        user = self._create_user()
        old_thread = self._create_thread(
            user_id=user.id,
            updated_at=dt.datetime(2026, 1, 1, 0, 0, 0),
        )
        latest_thread = self._create_thread(
            user_id=user.id,
            updated_at=dt.datetime(2026, 1, 1, 0, 0, 5),
        )
        self.assertNotEqual(old_thread.id, latest_thread.id)

        fake_server = types.SimpleNamespace(key="mcp-fs")
        fake_cfg = types.SimpleNamespace(sandbox=types.SimpleNamespace(time_limit_sec=88))
        fake_context = types.SimpleNamespace(sandbox=object())

        with (
            patch("app.api.mcps._must_get_user_mcp", return_value=fake_server),
            patch("app.api.mcps.load_config", return_value=fake_cfg),
            patch("app.api.mcps.get_or_create_daytona_backend", return_value=fake_context) as get_backend,
            patch(
                "app.api.mcps.build_mcp_client_entry",
                side_effect=RuntimeError("boom"),
            ) as build_entry,
        ):
            result = await test_mcp_connection("mcp-1", db=self.db, user=user)

        self.assertFalse(result.success)
        self.assertIn(latest_thread.id, result.message)
        get_backend.assert_called_once_with(
            thread_id=latest_thread.id,
            command_timeout_seconds=88,
            allow_create_if_missing=False,
        )
        build_entry.assert_called_once_with(
            fake_server,
            thread_id=latest_thread.id,
            daytona_sandbox=fake_context.sandbox,
        )

    async def test_returns_failure_when_no_thread_exists(self) -> None:
        user = self._create_user()
        fake_server = types.SimpleNamespace(key="mcp-fs")

        with (
            patch("app.api.mcps._must_get_user_mcp", return_value=fake_server),
            patch("app.api.mcps.load_config") as load_cfg,
            patch("app.api.mcps.get_or_create_daytona_backend") as get_backend,
        ):
            result = await test_mcp_connection("mcp-1", db=self.db, user=user)

        self.assertFalse(result.success)
        self.assertIn("No active session found", result.message)
        load_cfg.assert_not_called()
        get_backend.assert_not_called()

    async def test_returns_failure_when_latest_thread_sandbox_unavailable(self) -> None:
        user = self._create_user()
        latest_thread = self._create_thread(
            user_id=user.id,
            updated_at=dt.datetime(2026, 1, 1, 0, 0, 5),
        )

        fake_server = types.SimpleNamespace(key="mcp-fs")
        fake_cfg = types.SimpleNamespace(sandbox=types.SimpleNamespace(time_limit_sec=66))

        with (
            patch("app.api.mcps._must_get_user_mcp", return_value=fake_server),
            patch("app.api.mcps.load_config", return_value=fake_cfg),
            patch(
                "app.api.mcps.get_or_create_daytona_backend",
                side_effect=RuntimeError("sandbox missing"),
            ) as get_backend,
            patch("app.api.mcps.build_mcp_client_entry") as build_entry,
        ):
            result = await test_mcp_connection("mcp-1", db=self.db, user=user)

        self.assertFalse(result.success)
        self.assertIn("Sandbox unavailable", result.message)
        self.assertIn(latest_thread.id, result.message)
        get_backend.assert_called_once()
        build_entry.assert_not_called()

    async def test_uses_requested_thread_when_thread_id_is_provided(self) -> None:
        user = self._create_user()
        requested_thread = self._create_thread(
            user_id=user.id,
            updated_at=dt.datetime(2026, 1, 1, 0, 0, 0),
        )
        latest_thread = self._create_thread(
            user_id=user.id,
            updated_at=dt.datetime(2026, 1, 1, 0, 0, 5),
        )
        self.assertNotEqual(requested_thread.id, latest_thread.id)

        fake_server = types.SimpleNamespace(key="mcp-fs")
        fake_cfg = types.SimpleNamespace(sandbox=types.SimpleNamespace(time_limit_sec=88))
        fake_context = types.SimpleNamespace(sandbox=object())

        with (
            patch("app.api.mcps._must_get_user_mcp", return_value=fake_server),
            patch("app.api.mcps.load_config", return_value=fake_cfg),
            patch("app.api.mcps.get_or_create_daytona_backend", return_value=fake_context) as get_backend,
            patch(
                "app.api.mcps.build_mcp_client_entry",
                side_effect=RuntimeError("boom"),
            ) as build_entry,
        ):
            result = await test_mcp_connection(
                "mcp-1",
                payload=MCPServerTestIn(thread_id=requested_thread.id),
                db=self.db,
                user=user,
            )

        self.assertFalse(result.success)
        self.assertIn(requested_thread.id, result.message)
        self.assertNotIn(latest_thread.id, result.message)
        get_backend.assert_called_once_with(
            thread_id=requested_thread.id,
            command_timeout_seconds=88,
            allow_create_if_missing=False,
        )
        build_entry.assert_called_once_with(
            fake_server,
            thread_id=requested_thread.id,
            daytona_sandbox=fake_context.sandbox,
        )

    async def test_returns_failure_when_requested_thread_is_not_owned(self) -> None:
        user = self._create_user()
        fake_server = types.SimpleNamespace(key="mcp-fs")

        with (
            patch("app.api.mcps._must_get_user_mcp", return_value=fake_server),
            patch("app.api.mcps.load_config") as load_cfg,
            patch("app.api.mcps.get_or_create_daytona_backend") as get_backend,
        ):
            result = await test_mcp_connection(
                "mcp-1",
                payload=MCPServerTestIn(thread_id="missing-thread-id"),
                db=self.db,
                user=user,
            )

        self.assertFalse(result.success)
        self.assertIn("missing-thread-id", result.message)
        load_cfg.assert_not_called()
        get_backend.assert_not_called()

    async def test_returns_success_when_tools_loaded_from_sandbox(self) -> None:
        user = self._create_user()
        latest_thread = self._create_thread(
            user_id=user.id,
            updated_at=dt.datetime(2026, 1, 1, 0, 0, 5),
        )

        fake_server = types.SimpleNamespace(key="mcp-fs")
        fake_cfg = types.SimpleNamespace(sandbox=types.SimpleNamespace(time_limit_sec=99))
        fake_context = types.SimpleNamespace(sandbox=object())

        with (
            patch("app.api.mcps._must_get_user_mcp", return_value=fake_server),
            patch("app.api.mcps.load_config", return_value=fake_cfg),
            patch("app.api.mcps.get_or_create_daytona_backend", return_value=fake_context),
            patch(
                "app.api.mcps.build_mcp_client_entry",
                return_value={"transport": "streamable_http", "url": "http://test/mcp"},
            ),
            patch("app.api.mcps.MultiServerMCPClient", _FakeMCPClient),
        ):
            result = await test_mcp_connection("mcp-1", db=self.db, user=user)

        self.assertTrue(result.success)
        self.assertIn(latest_thread.id, result.message)
        self.assertEqual(result.tool_count, 1)
        self.assertEqual(result.tools, ["mcp-fs_list_directory"])

    async def test_returns_failure_when_tool_discovery_times_out(self) -> None:
        user = self._create_user()
        latest_thread = self._create_thread(
            user_id=user.id,
            updated_at=dt.datetime(2026, 1, 1, 0, 0, 5),
        )

        fake_server = types.SimpleNamespace(key="web-fetch")
        fake_cfg = types.SimpleNamespace(sandbox=types.SimpleNamespace(time_limit_sec=99))
        fake_context = types.SimpleNamespace(sandbox=object())

        async def _timeout_wait_for(awaitable, timeout):
            if hasattr(awaitable, "close"):
                awaitable.close()
            raise asyncio.TimeoutError

        with (
            patch("app.api.mcps._must_get_user_mcp", return_value=fake_server),
            patch("app.api.mcps.load_config", return_value=fake_cfg),
            patch("app.api.mcps.get_or_create_daytona_backend", return_value=fake_context),
            patch(
                "app.api.mcps.build_mcp_client_entry",
                return_value={"transport": "streamable_http", "url": "http://test/mcp"},
            ),
            patch("app.api.mcps.MultiServerMCPClient", _FakeMCPClient),
            patch(
                "app.api.mcps.asyncio.wait_for",
                new=_timeout_wait_for,
            ),
        ):
            result = await test_mcp_connection("mcp-1", db=self.db, user=user)

        self.assertFalse(result.success)
        self.assertIn("timed out", result.message.lower())
        self.assertIn(str(MCP_TEST_CONNECT_TIMEOUT_SECONDS), result.message)
        self.assertIn(latest_thread.id, result.message)
        self.assertEqual(result.tool_count, 0)
        self.assertEqual(result.tools, [])


if __name__ == "__main__":
    unittest.main()
