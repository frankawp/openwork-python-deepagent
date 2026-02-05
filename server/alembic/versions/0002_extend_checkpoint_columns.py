"""extend checkpoint columns to longtext

Revision ID: 0002
Revises: 0001
Create Date: 2026-02-03
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 将 checkpoint 和 metadata 列从 TEXT 改为 LONGTEXT
    # MySQL: TEXT = 64KB, LONGTEXT = 4GB
    op.execute("ALTER TABLE checkpoints MODIFY COLUMN checkpoint LONGTEXT")
    op.execute("ALTER TABLE checkpoints MODIFY COLUMN metadata LONGTEXT")
    # writes 表的 value 列也可能需要
    op.execute("ALTER TABLE writes MODIFY COLUMN value LONGTEXT")


def downgrade() -> None:
    op.execute("ALTER TABLE checkpoints MODIFY COLUMN checkpoint TEXT")
    op.execute("ALTER TABLE checkpoints MODIFY COLUMN metadata TEXT")
    op.execute("ALTER TABLE writes MODIFY COLUMN value TEXT")
