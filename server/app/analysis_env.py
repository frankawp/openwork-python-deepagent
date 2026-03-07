from __future__ import annotations

from pathlib import Path

DEFAULT_REQUIREMENTS = """pandas
numpy
matplotlib
seaborn
scipy
statsmodels
"""


def _ensure_directories(root: Path) -> None:
    (root / "analysis" / "inputs").mkdir(parents=True, exist_ok=True)
    (root / "analysis" / "scripts").mkdir(parents=True, exist_ok=True)
    (root / "analysis" / "figures").mkdir(parents=True, exist_ok=True)
    (root / "analysis" / "outputs").mkdir(parents=True, exist_ok=True)


def _write_requirements(requirements_path: Path) -> None:
    if not requirements_path.exists():
        requirements_path.write_text(DEFAULT_REQUIREMENTS, encoding="utf-8")


def ensure_analysis_workspace_layout(workspace_root: str) -> None:
    root = Path(workspace_root)
    _ensure_directories(root)
    requirements_path = root / "analysis" / "requirements.txt"
    _write_requirements(requirements_path)
