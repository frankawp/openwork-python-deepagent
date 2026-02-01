"""initial schema

Revision ID: 0001
Revises: 
Create Date: 2026-01-31
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("username", sa.String(length=64), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("is_admin", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)
    op.create_index("ix_users_username", "users", ["username"], unique=True)

    op.create_table(
        "threads",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=True),
        sa.Column("thread_values", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
    )
    op.create_index("ix_threads_user_id", "threads", ["user_id"], unique=False)

    op.create_table(
        "runs",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("thread_id", sa.String(length=36), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("metadata", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["thread_id"], ["threads.id"]),
    )
    op.create_index("ix_runs_thread_id", "runs", ["thread_id"], unique=False)

    op.create_table(
        "global_api_keys",
        sa.Column("provider", sa.String(length=64), primary_key=True),
        sa.Column("encrypted_key", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )

    op.create_table(
        "app_settings",
        sa.Column("key", sa.String(length=128), primary_key=True),
        sa.Column("value", sa.Text(), nullable=False),
    )

    op.create_table(
        "checkpoints",
        sa.Column("thread_id", sa.String(length=36), primary_key=True),
        sa.Column("checkpoint_ns", sa.String(length=255), primary_key=True),
        sa.Column("checkpoint_id", sa.String(length=255), primary_key=True),
        sa.Column("parent_checkpoint_id", sa.String(length=255), nullable=True),
        sa.Column("type", sa.String(length=255), nullable=True),
        sa.Column("checkpoint", sa.Text(), nullable=True),
        sa.Column("metadata", sa.Text(), nullable=True),
    )

    op.create_table(
        "writes",
        sa.Column("thread_id", sa.String(length=36), primary_key=True),
        sa.Column("checkpoint_ns", sa.String(length=255), primary_key=True),
        sa.Column("checkpoint_id", sa.String(length=255), primary_key=True),
        sa.Column("task_id", sa.String(length=255), primary_key=True),
        sa.Column("idx", sa.Integer(), primary_key=True),
        sa.Column("channel", sa.String(length=255), nullable=False),
        sa.Column("type", sa.String(length=255), nullable=True),
        sa.Column("value", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("writes")
    op.drop_table("checkpoints")
    op.drop_table("app_settings")
    op.drop_table("global_api_keys")
    op.drop_index("ix_runs_thread_id", table_name="runs")
    op.drop_table("runs")
    op.drop_index("ix_threads_user_id", table_name="threads")
    op.drop_table("threads")
    op.drop_index("ix_users_username", table_name="users")
    op.drop_index("ix_users_email", table_name="users")
    op.drop_table("users")
