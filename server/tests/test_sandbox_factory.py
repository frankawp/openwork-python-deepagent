import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.config import SandboxConfig
from app.sandbox import LocalSandbox, NsjailSandbox, build_sandbox


def make_sandbox_config(**overrides) -> SandboxConfig:
    data = {
        "enabled": True,
        "nsjail_path": "nsjail",
        "rootfs_dir": ".sandbox-root",
        "readonly_bind_mounts": ["/bin", "/usr", "/usr/local", "/lib", "/lib64", "/etc"],
        "mount_dev": True,
        "mount_proc": False,
        "rlimit_as_mb": 1024,
        "rlimit_cpu_sec": 120,
        "rlimit_fsize_mb": 512,
        "time_limit_sec": 120,
        "max_output_bytes": 1000,
        "seccomp_profile": "strict",
        "seccomp_profiles": {},
        "seccomp": "",
    }
    data.update(overrides)
    return SandboxConfig(**data)


class SandboxFactoryTests(unittest.TestCase):
    def test_raises_when_sandbox_disabled(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            with self.assertRaisesRegex(RuntimeError, "Sandbox is required"):
                build_sandbox(tmpdir, make_sandbox_config(enabled=False))

    def test_returns_local_sandbox_on_non_linux(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            with (
                patch("app.sandbox.platform.system", return_value="Darwin"),
                self.assertLogs("app.sandbox", level="WARNING") as logs,
            ):
                sandbox = build_sandbox(tmpdir, make_sandbox_config())

            self.assertIsInstance(sandbox, LocalSandbox)
            self.assertTrue(
                any("Falling back to LocalSandbox" in entry for entry in logs.output)
            )

    def test_returns_nsjail_sandbox_on_linux_when_binary_exists(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            fake_nsjail = Path(tmpdir) / "fake_nsjail"
            fake_nsjail.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            fake_nsjail.chmod(0o755)
            with (
                patch("app.sandbox.platform.system", return_value="Linux"),
                patch("app.sandbox.shutil.which", return_value=str(fake_nsjail)),
            ):
                sandbox = build_sandbox(tmpdir, make_sandbox_config())

            self.assertIsInstance(sandbox, NsjailSandbox)

    def test_falls_back_on_linux_when_nsjail_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            with (
                patch("app.sandbox.platform.system", return_value="Linux"),
                patch("app.sandbox.shutil.which", return_value=None),
                self.assertLogs("app.sandbox", level="WARNING") as logs,
            ):
                sandbox = build_sandbox(tmpdir, make_sandbox_config(nsjail_path="missing-nsjail"))

            self.assertIsInstance(sandbox, LocalSandbox)
            self.assertTrue(any("nsjail not found" in entry for entry in logs.output))


if __name__ == "__main__":
    unittest.main()
