"""add skills tables

Revision ID: 0003
Revises: 0002
Create Date: 2026-03-10
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "skills",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("key", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("user_id", "key", name="uq_skills_user_key"),
    )
    op.create_index("ix_skills_user_id", "skills", ["user_id"], unique=False)

    op.create_table(
        "skill_files",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("skill_id", sa.String(length=36), nullable=False),
        sa.Column("path", sa.String(length=512), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("checksum", sa.String(length=64), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["skill_id"], ["skills.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("skill_id", "path", name="uq_skill_files_skill_path"),
    )
    op.create_index("ix_skill_files_skill_id", "skill_files", ["skill_id"], unique=False)

    op.create_table(
        "thread_skill_bindings",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("thread_id", sa.String(length=36), nullable=False),
        sa.Column("skill_id", sa.String(length=36), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["thread_id"], ["threads.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["skill_id"], ["skills.id"], ondelete="CASCADE"),
        sa.UniqueConstraint(
            "thread_id",
            "skill_id",
            name="uq_thread_skill_bindings_thread_skill",
        ),
        sa.UniqueConstraint(
            "thread_id",
            "position",
            name="uq_thread_skill_bindings_thread_position",
        ),
    )
    op.create_index(
        "ix_thread_skill_bindings_thread_id",
        "thread_skill_bindings",
        ["thread_id"],
        unique=False,
    )
    op.create_index(
        "ix_thread_skill_bindings_skill_id",
        "thread_skill_bindings",
        ["skill_id"],
        unique=False,
    )

    op.create_table(
        "thread_skill_materialization_state",
        sa.Column("thread_id", sa.String(length=36), primary_key=True),
        sa.Column("desired_hash", sa.String(length=64), nullable=True),
        sa.Column("materialized_hash", sa.String(length=64), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False, server_default=sa.text("'ready'")),
        sa.Column("materialized_root", sa.String(length=1024), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["thread_id"], ["threads.id"], ondelete="CASCADE"),
    )


def downgrade() -> None:
    op.drop_table("thread_skill_materialization_state")
    op.drop_index("ix_thread_skill_bindings_skill_id", table_name="thread_skill_bindings")
    op.drop_index("ix_thread_skill_bindings_thread_id", table_name="thread_skill_bindings")
    op.drop_table("thread_skill_bindings")
    op.drop_index("ix_skill_files_skill_id", table_name="skill_files")
    op.drop_table("skill_files")
    op.drop_index("ix_skills_user_id", table_name="skills")
    op.drop_table("skills")
