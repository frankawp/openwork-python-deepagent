"""add mcp tables

Revision ID: 0004
Revises: 0003
Create Date: 2026-03-11
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "mcp_servers",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("key", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("transport", sa.String(length=32), nullable=False),
        sa.Column("config", sa.JSON(), nullable=False),
        sa.Column("encrypted_secret_json", sa.Text(), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("user_id", "key", name="uq_mcp_servers_user_key"),
    )
    op.create_index("ix_mcp_servers_user_id", "mcp_servers", ["user_id"], unique=False)

    op.create_table(
        "thread_mcp_bindings",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("thread_id", sa.String(length=36), nullable=False),
        sa.Column("mcp_id", sa.String(length=36), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["thread_id"], ["threads.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["mcp_id"], ["mcp_servers.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("thread_id", "mcp_id", name="uq_thread_mcp_bindings_thread_mcp"),
        sa.UniqueConstraint(
            "thread_id",
            "position",
            name="uq_thread_mcp_bindings_thread_position",
        ),
    )
    op.create_index(
        "ix_thread_mcp_bindings_thread_id",
        "thread_mcp_bindings",
        ["thread_id"],
        unique=False,
    )
    op.create_index(
        "ix_thread_mcp_bindings_mcp_id",
        "thread_mcp_bindings",
        ["mcp_id"],
        unique=False,
    )

    op.create_table(
        "thread_mcp_runtime_state",
        sa.Column("thread_id", sa.String(length=36), primary_key=True),
        sa.Column("status", sa.String(length=16), nullable=False, server_default=sa.text("'ready'")),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["thread_id"], ["threads.id"], ondelete="CASCADE"),
    )


def downgrade() -> None:
    op.drop_table("thread_mcp_runtime_state")
    op.drop_index("ix_thread_mcp_bindings_mcp_id", table_name="thread_mcp_bindings")
    op.drop_index("ix_thread_mcp_bindings_thread_id", table_name="thread_mcp_bindings")
    op.drop_table("thread_mcp_bindings")
    op.drop_index("ix_mcp_servers_user_id", table_name="mcp_servers")
    op.drop_table("mcp_servers")
