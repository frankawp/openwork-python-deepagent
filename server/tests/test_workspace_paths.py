import unittest

from fastapi import HTTPException

from app.api.workspace import _safe_sandbox_path


class WorkspacePathSafetyTests(unittest.TestCase):
    def test_allows_relative_path_within_workspace(self) -> None:
        result = _safe_sandbox_path("/home/daytona", "analysis/report.md")
        self.assertEqual(result, "/home/daytona/analysis/report.md")

    def test_allows_workspace_absolute_path(self) -> None:
        result = _safe_sandbox_path(
            "/home/daytona",
            "/home/daytona/analysis/report.md",
        )
        self.assertEqual(result, "/home/daytona/analysis/report.md")

    def test_rejects_parent_directory_escape(self) -> None:
        with self.assertRaises(HTTPException) as ctx:
            _safe_sandbox_path("/home/daytona", "../secrets.txt")
        self.assertEqual(ctx.exception.status_code, 403)

    def test_rejects_prefix_confusion_escape(self) -> None:
        with self.assertRaises(HTTPException) as ctx:
            _safe_sandbox_path("/home/daytona", "/home/daytona2/data.txt")
        self.assertEqual(ctx.exception.status_code, 403)


if __name__ == "__main__":
    unittest.main()
