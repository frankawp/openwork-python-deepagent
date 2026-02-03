"""Skills 功能模块 - 管理用户技能目录和示例技能"""

from pathlib import Path

from .config import load_config

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


def init_user_skills(username: str) -> Path:
    """初始化用户的 skills 目录，返回 skills 目录路径

    Args:
        username: 用户名

    Returns:
        skills 目录的 Path 对象
    """
    cfg = load_config()
    skills_dir = Path(cfg.workspace.root) / username / "skills"
    skills_dir.mkdir(parents=True, exist_ok=True)

    # 创建示例技能（如果不存在）
    example_skill_dir = skills_dir / "example-skill"
    if not example_skill_dir.exists():
        example_skill_dir.mkdir(exist_ok=True)
        (example_skill_dir / "SKILL.md").write_text(EXAMPLE_SKILL)

    return skills_dir


def get_user_skills_path(username: str) -> Path | None:
    """获取用户的 skills 目录路径

    Args:
        username: 用户名

    Returns:
        skills 目录的 Path 对象，如果目录不存在则返回 None
    """
    cfg = load_config()
    skills_dir = Path(cfg.workspace.root) / username / "skills"
    return skills_dir if skills_dir.exists() else None
