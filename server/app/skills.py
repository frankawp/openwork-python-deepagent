"""Skills 功能模块 - 管理用户技能目录和示例技能"""

from pathlib import Path

from .workspace_paths import user_workspace_path

# 示例技能内容
EXAMPLE_SKILL = """---
name: example-skill
description: A example skill demonstrating how to create custom skills
---

# Example Skill

This is an example skill to demonstrate the skills system.

## When to Use
- When you want to create custom workflows
- When you need specialized task handling

## Instructions
1. Create a new directory under your skills folder
2. Add a SKILL.md file with YAML frontmatter
3. Write your skill instructions in markdown

## Example

For a web research skill, you might create:
```
skills/
└── web-research/
    └── SKILL.md
```

The SKILL.md file should contain:
- YAML frontmatter with `name` and `description`
- Detailed instructions in markdown format
"""

AB_TEST_SKILL = """---
name: ab-test
description: AB test analysis workflow and guardrails
---

# AB Test Skill

## When to Use
- When the user asks for AB test analysis or experiment results.
- When working with CSV data containing experiment groups.

## Required Fields (preferred)
- `user_id`
- `group` (control/treatment)
- `event_date`
- `metric` (numeric)

If fields differ, document the mapping in `analysis/notes.md`.

## Standard Steps
1. Validate data: missing values, outliers, duplicate users.
2. Define metrics and aggregation windows.
3. Compute group-level summaries and effect size.
4. Run significance tests (t-test or non-parametric when needed).
5. Provide confidence intervals and practical impact interpretation.

## Common Pitfalls
- Mixing pre- and post-experiment windows.
- Multiple testing without correction.
- Metric skew (use log transform or non-parametric tests).

## Outputs
- `analysis/notes.md`: assumptions and data checks
- `analysis/outputs/*.csv`: intermediate tables
- `analysis/figures/*.png`: plots
- `analysis/report.md`: conclusions and recommendations
"""


def init_workspace_skills(workspace_root: str) -> Path:
    """初始化 workspace 的 skills 目录，返回 skills 目录路径

    Args:
        workspace_root: workspace 根目录

    Returns:
        skills 目录的 Path 对象
    """
    skills_dir = Path(workspace_root) / "skills"
    skills_dir.mkdir(parents=True, exist_ok=True)

    # 创建示例技能（如果不存在）
    example_skill_dir = skills_dir / "example-skill"
    if not example_skill_dir.exists():
        example_skill_dir.mkdir(exist_ok=True)
        (example_skill_dir / "SKILL.md").write_text(EXAMPLE_SKILL, encoding="utf-8")

    ab_test_dir = skills_dir / "ab-test"
    if not ab_test_dir.exists():
        ab_test_dir.mkdir(exist_ok=True)
        (ab_test_dir / "SKILL.md").write_text(AB_TEST_SKILL, encoding="utf-8")

    return skills_dir


def init_user_skills(username: str) -> Path:
    """初始化用户的 skills 目录，返回 skills 目录路径

    Args:
        username: 用户名

    Returns:
        skills 目录的 Path 对象
    """
    workspace_root = user_workspace_path(username, create=True)
    return init_workspace_skills(str(workspace_root))


def get_workspace_skills_path(workspace_root: str) -> Path | None:
    """获取 workspace 的 skills 目录路径

    Args:
        workspace_root: workspace 根目录

    Returns:
        skills 目录的 Path 对象，如果目录不存在则返回 None
    """
    skills_dir = Path(workspace_root) / "skills"
    return skills_dir if skills_dir.exists() else None
