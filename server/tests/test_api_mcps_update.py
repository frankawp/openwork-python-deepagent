from __future__ import annotations

import datetime as dt
import unittest
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.api.mcps import update_mcp
from app.db import Base
from app.models import MCPServer, User
from app.schemas import MCPServerUpdate


class McpUpdateSyncTests(unittest.TestCase):
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

    def _create_mcp(self, *, user_id: str) -> MCPServer:
        now = dt.datetime.utcnow()
        mcp = MCPServer(
            user_id=user_id,
            key="mcp-fs",
            name="Filesystem",
            description="Test MCP",
            transport="streamable_http",
            config_json={"url": "http://127.0.0.1:8001/mcp"},
            encrypted_secret_json=None,
            enabled=True,
            created_at=now,
            updated_at=now,
        )
        self.db.add(mcp)
        self.db.commit()
        self.db.refresh(mcp)
        return mcp

    def test_name_description_only_update_does_not_sync_bindings(self) -> None:
        user = self._create_user()
        mcp = self._create_mcp(user_id=user.id)

        with (
            patch("app.api.mcps.sync_user_mcp_bindings") as sync_bindings,
            patch("app.api.mcps._clear_mcp_tools_cache") as clear_cache,
        ):
            out = update_mcp(
                mcp.id,
                MCPServerUpdate(name="Filesystem MCP", description="Updated description"),
                db=self.db,
                user=user,
            )

        self.assertEqual(out.name, "Filesystem MCP")
        self.assertEqual(out.description, "Updated description")
        sync_bindings.assert_not_called()
        clear_cache.assert_not_called()

    def test_enabled_change_syncs_bindings_and_clears_cache(self) -> None:
        user = self._create_user()
        mcp = self._create_mcp(user_id=user.id)

        with (
            patch("app.api.mcps.sync_user_mcp_bindings", return_value=["thread-1"]) as sync_bindings,
            patch("app.api.mcps._clear_mcp_tools_cache") as clear_cache,
        ):
            out = update_mcp(
                mcp.id,
                MCPServerUpdate(enabled=False),
                db=self.db,
                user=user,
            )

        self.assertFalse(out.enabled)
        sync_bindings.assert_called_once_with(self.db, user_id=user.id)
        clear_cache.assert_called_once_with(["thread-1"])

    def test_same_runtime_payload_does_not_sync_bindings(self) -> None:
        user = self._create_user()
        mcp = self._create_mcp(user_id=user.id)

        with (
            patch("app.api.mcps.sync_user_mcp_bindings") as sync_bindings,
            patch("app.api.mcps._clear_mcp_tools_cache") as clear_cache,
        ):
            out = update_mcp(
                mcp.id,
                MCPServerUpdate(
                    transport="streamable_http",
                    config={"url": "http://127.0.0.1:8001/mcp"},
                ),
                db=self.db,
                user=user,
            )

        self.assertEqual(out.transport, "streamable_http")
        self.assertEqual(out.config, {"url": "http://127.0.0.1:8001/mcp"})
        sync_bindings.assert_not_called()
        clear_cache.assert_not_called()


if __name__ == "__main__":
    unittest.main()

