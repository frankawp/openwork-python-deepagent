import tempfile
import unittest
from pathlib import Path

from app.analysis_env import ensure_analysis_environment
from app.sandbox.types import ExecuteResult


class FakeSandbox:
    def __init__(self) -> None:
        self.commands: list[str] = []

    def run(self, command: str, *, env=None, timeout_seconds=None, max_output_bytes=None) -> ExecuteResult:
        self.commands.append(command)
        return ExecuteResult(output="ok", exit_code=0, truncated=False)


class AnalysisEnvTests(unittest.TestCase):
    def test_creates_analysis_dirs_and_venv(self) -> None:
        sandbox = FakeSandbox()
        with tempfile.TemporaryDirectory() as tmpdir:
            ensure_analysis_environment(tmpdir, sandbox)

            root = Path(tmpdir)
            self.assertTrue((root / "analysis" / "inputs").exists())
            self.assertTrue((root / "analysis" / "scripts").exists())
            self.assertTrue((root / "analysis" / "figures").exists())
            self.assertTrue((root / "analysis" / "outputs").exists())
            self.assertTrue((root / "analysis" / "requirements.txt").exists())
            self.assertTrue((root / ".venv").exists())

            self.assertIn("uv venv .venv", sandbox.commands)
            self.assertIn(
                ".venv/bin/uv pip install -r analysis/requirements.txt",
                sandbox.commands,
            )

    def test_skips_venv_when_present(self) -> None:
        sandbox = FakeSandbox()
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / ".venv").mkdir(parents=True, exist_ok=True)

            ensure_analysis_environment(tmpdir, sandbox)

            self.assertNotIn("uv venv .venv", sandbox.commands)


if __name__ == "__main__":
    unittest.main()
