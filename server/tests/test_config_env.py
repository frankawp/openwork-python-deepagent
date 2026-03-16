from __future__ import annotations

import os
import tempfile
import textwrap
import unittest
from pathlib import Path
from unittest.mock import patch

import app.config as config_module


class ConfigEnvTests(unittest.TestCase):
    def setUp(self) -> None:
        self._original_config = config_module._CONFIG
        self._original_env_loaded = config_module._ENV_LOADED
        config_module._CONFIG = None
        config_module._ENV_LOADED = False

    def tearDown(self) -> None:
        config_module._CONFIG = self._original_config
        config_module._ENV_LOADED = self._original_env_loaded

    def test_load_config_reads_env_file_and_populates_runtime_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            env_path = Path(tmpdir) / ".env"
            env_path.write_text(
                textwrap.dedent(
                    """
                    DATABASE_URL=mysql+pymysql://user:pass@host:3306/openwork
                    JWT_SECRET="secret-123"
                    ACCESS_TTL_MIN=90
                    REFRESH_TTL_DAYS=14
                    WORKSPACE_ROOT=/tmp/workspaces
                    DATA_DIR=/tmp/data
                    ADMIN_EMAIL=admin@example.com
                    ADMIN_PASSWORD='admin123'
                    SANDBOX_ENABLED=false
                    SANDBOX_TIME_LIMIT_SEC=180
                    SANDBOX_MAX_OUTPUT_BYTES=2048
                    DAYTONA_API_KEY=dtn_test
                    DAYTONA_API_URL=https://app.daytona.io/api
                    DAYTONA_TARGET=us
                    DAYTONA_SNAPSHOT=snapshot-1
                    DAYTONA_AUTO_STOP_INTERVAL_MIN=15
                    DAYTONA_AUTO_ARCHIVE_INTERVAL_DAYS=2
                    DAYTONA_AUTO_DELETE_INTERVAL_DAYS=3
                    """
                ).strip()
                + "\n",
                encoding="utf-8",
            )

            with patch.dict(os.environ, {}, clear=True):
                cfg = config_module.load_config(str(env_path))

            self.assertEqual(cfg.database.url, "mysql+pymysql://user:pass@host:3306/openwork")
            self.assertEqual(cfg.auth.jwt_secret, "secret-123")
            self.assertEqual(cfg.auth.access_ttl_min, 90)
            self.assertEqual(cfg.auth.refresh_ttl_days, 14)
            self.assertEqual(cfg.workspace.root, "/tmp/workspaces")
            self.assertEqual(cfg.data.dir, "/tmp/data")
            self.assertEqual(cfg.admin.email, "admin@example.com")
            self.assertEqual(cfg.admin.password, "admin123")
            self.assertFalse(cfg.sandbox.enabled)
            self.assertEqual(cfg.sandbox.time_limit_sec, 180)
            self.assertEqual(cfg.sandbox.max_output_bytes, 2048)
            self.assertEqual(cfg.sandbox.daytona_auto_stop_interval_min, 15)
            self.assertEqual(cfg.sandbox.daytona_auto_archive_interval_days, 2)
            self.assertEqual(cfg.sandbox.daytona_auto_delete_interval_days, 3)
            self.assertEqual(cfg.daytona.api_key, "dtn_test")
            self.assertEqual(cfg.daytona.api_url, "https://app.daytona.io/api")
            self.assertEqual(cfg.daytona.target, "us")
            self.assertEqual(cfg.daytona.snapshot, "snapshot-1")

    def test_load_config_uses_defaults_for_optional_values(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            env_path = Path(tmpdir) / ".env"
            env_path.write_text(
                textwrap.dedent(
                    """
                    DATABASE_URL=mysql+pymysql://user:pass@host:3306/openwork
                    JWT_SECRET=secret-123
                    WORKSPACE_ROOT=/tmp/workspaces
                    DATA_DIR=/tmp/data
                    ADMIN_EMAIL=admin@example.com
                    ADMIN_PASSWORD=admin123
                    DAYTONA_API_KEY=dtn_test
                    """
                ).strip()
                + "\n",
                encoding="utf-8",
            )

            with patch.dict(os.environ, {}, clear=True):
                cfg = config_module.load_config(str(env_path))

            self.assertEqual(cfg.auth.access_ttl_min, 60)
            self.assertEqual(cfg.auth.refresh_ttl_days, 7)
            self.assertTrue(cfg.sandbox.enabled)
            self.assertEqual(cfg.sandbox.time_limit_sec, 120)
            self.assertEqual(cfg.sandbox.max_output_bytes, 100_000)
            self.assertEqual(cfg.sandbox.daytona_auto_stop_interval_min, 0)
            self.assertEqual(cfg.sandbox.daytona_auto_archive_interval_days, 0)
            self.assertEqual(cfg.sandbox.daytona_auto_delete_interval_days, -1)
            self.assertIsNone(cfg.daytona.api_url)
            self.assertIsNone(cfg.daytona.target)
            self.assertIsNone(cfg.daytona.snapshot)


if __name__ == "__main__":
    unittest.main()
