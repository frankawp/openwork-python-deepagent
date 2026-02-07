import os
import tempfile
import unittest
from pathlib import Path

from app.agent_tools import _rewrite_virtual_paths_in_command


class RewriteVirtualPathsTests(unittest.TestCase):
    def test_rewrites_virtual_absolute_path_when_system_path_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace_root = Path(tmpdir)
            (workspace_root / "fibonacci.py").write_text("print('ok')")

            cmd = "python3 /fibonacci.py"
            rewritten = _rewrite_virtual_paths_in_command(cmd, str(workspace_root))

            self.assertIn(str(workspace_root / "fibonacci.py"), rewritten)

    def test_keeps_existing_system_absolute_path(self) -> None:
        with tempfile.NamedTemporaryFile() as tmpfile:
            workspace_root = Path(tempfile.mkdtemp())
            cmd = f"python3 {tmpfile.name}"
            rewritten = _rewrite_virtual_paths_in_command(cmd, str(workspace_root))
            self.assertEqual(cmd, rewritten)

    def test_rewrites_nonexistent_absolute_path_for_creation(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace_root = Path(tmpdir)
            cmd = "touch /analysis/outputs/new_file.csv"
            rewritten = _rewrite_virtual_paths_in_command(cmd, str(workspace_root))
            expected = str(workspace_root / "analysis/outputs/new_file.csv")
            self.assertIn(expected, rewritten)

    def test_env_assignment_is_rewritten(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace_root = Path(tmpdir)
            cmd = "DATA=/analysis/inputs/data.csv python3 script.py"
            rewritten = _rewrite_virtual_paths_in_command(cmd, str(workspace_root))
            expected = f"DATA={workspace_root / 'analysis/inputs/data.csv'}"
            self.assertIn(expected, rewritten)

    def test_relative_path_is_unchanged(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace_root = Path(tmpdir)
            cmd = "python3 fibonacci.py"
            rewritten = _rewrite_virtual_paths_in_command(cmd, str(workspace_root))
            self.assertEqual(cmd, rewritten)

    def test_glob_path_is_unchanged(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace_root = Path(tmpdir)
            cmd = "ls /**/*.py"
            rewritten = _rewrite_virtual_paths_in_command(cmd, str(workspace_root))
            self.assertEqual(cmd, rewritten)


if __name__ == "__main__":
    unittest.main()
