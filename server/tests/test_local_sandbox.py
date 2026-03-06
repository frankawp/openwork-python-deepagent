import tempfile
import unittest
from pathlib import Path

from app.config import SandboxConfig
from app.sandbox.local_sandbox import LocalSandbox


def make_sandbox_config(**overrides) -> SandboxConfig:
    data = {
        "enabled": True,
        "nsjail_path": "nsjail",
        "allow_local_fallback": True,
        "disable_clone_newns": False,
        "rootfs_dir": ".sandbox-root",
        "readonly_bind_mounts": ["/bin", "/usr", "/usr/local", "/lib", "/lib64", "/etc"],
        "mount_dev": True,
        "mount_proc": False,
        "rlimit_as_mb": 1024,
        "rlimit_cpu_sec": 120,
        "rlimit_fsize_mb": 512,
        "time_limit_sec": 2,
        "max_output_bytes": 1000,
        "seccomp_profile": "strict",
        "seccomp_profiles": {},
        "seccomp": "",
    }
    data.update(overrides)
    return SandboxConfig(**data)


class LocalSandboxTests(unittest.TestCase):
    def test_runs_command_in_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            sandbox = LocalSandbox(tmpdir, make_sandbox_config())
            result = sandbox.run("pwd")

            self.assertEqual(result.exit_code, 0)
            self.assertFalse(result.truncated)
            self.assertIn(str(Path(tmpdir)), result.output)

    def test_times_out_long_running_command(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            sandbox = LocalSandbox(tmpdir, make_sandbox_config(time_limit_sec=1))
            result = sandbox.run("sleep 3")

            self.assertIsNone(result.exit_code)
            self.assertFalse(result.truncated)
            self.assertIn("timed out", result.output.lower())

    def test_truncates_large_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            sandbox = LocalSandbox(tmpdir, make_sandbox_config(max_output_bytes=40))
            result = sandbox.run("python3 -c \"print('a' * 500)\"")

            self.assertEqual(result.exit_code, 0)
            self.assertTrue(result.truncated)
            self.assertIn("Output truncated", result.output)


if __name__ == "__main__":
    unittest.main()
