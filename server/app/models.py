from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from .db import Base


def _uuid() -> str:
    return str(uuid.uuid4())


class User(Base):
    __tablename__ = "users"

    id = Column(String(36), primary_key=True, default=_uuid)
    username = Column(String(64), unique=True, nullable=False, index=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    is_admin = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=dt.datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=dt.datetime.utcnow, nullable=False)

    threads = relationship("Thread", back_populates="user", cascade="all, delete-orphan")
    skills = relationship("Skill", back_populates="user", cascade="all, delete-orphan")
    mcp_servers = relationship(
        "MCPServer", back_populates="user", cascade="all, delete-orphan"
    )


class Thread(Base):
    __tablename__ = "threads"

    id = Column(String(36), primary_key=True, default=_uuid)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    status = Column(String(32), default="idle", nullable=False)
    title = Column(String(255), nullable=True)
    metadata_json = Column("metadata", JSON, nullable=True)
    thread_values = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=dt.datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=dt.datetime.utcnow, nullable=False)

    user = relationship("User", back_populates="threads")
    skill_bindings = relationship(
        "ThreadSkillBinding", back_populates="thread", cascade="all, delete-orphan"
    )
    skill_materialization_state = relationship(
        "ThreadSkillMaterializationState",
        back_populates="thread",
        cascade="all, delete-orphan",
        uselist=False,
    )
    mcp_bindings = relationship(
        "ThreadMCPBinding", back_populates="thread", cascade="all, delete-orphan"
    )
    mcp_runtime_state = relationship(
        "ThreadMCPRuntimeState",
        back_populates="thread",
        cascade="all, delete-orphan",
        uselist=False,
    )


class Run(Base):
    __tablename__ = "runs"

    id = Column(String(36), primary_key=True, default=_uuid)
    thread_id = Column(String(36), ForeignKey("threads.id"), nullable=False, index=True)
    status = Column(String(32), nullable=False)
    metadata_json = Column("metadata", JSON, nullable=True)
    created_at = Column(DateTime, default=dt.datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=dt.datetime.utcnow, nullable=False)


class GlobalApiKey(Base):
    __tablename__ = "global_api_keys"

    provider = Column(String(64), primary_key=True)
    encrypted_key = Column(Text, nullable=False)
    updated_at = Column(DateTime, default=dt.datetime.utcnow, nullable=False)


class AppSetting(Base):
    __tablename__ = "app_settings"

    key = Column(String(128), primary_key=True)
    value = Column(Text, nullable=False)


class Skill(Base):
    __tablename__ = "skills"
    __table_args__ = (UniqueConstraint("user_id", "key", name="uq_skills_user_key"),)

    id = Column(String(36), primary_key=True, default=_uuid)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    key = Column(String(64), nullable=False)
    name = Column(String(128), nullable=False)
    description = Column(Text, nullable=False)
    enabled = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=dt.datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=dt.datetime.utcnow, nullable=False)

    user = relationship("User", back_populates="skills")
    files = relationship("SkillFile", back_populates="skill", cascade="all, delete-orphan")
    thread_bindings = relationship(
        "ThreadSkillBinding", back_populates="skill", cascade="all, delete-orphan"
    )


class SkillFile(Base):
    __tablename__ = "skill_files"
    __table_args__ = (UniqueConstraint("skill_id", "path", name="uq_skill_files_skill_path"),)

    id = Column(String(36), primary_key=True, default=_uuid)
    skill_id = Column(String(36), ForeignKey("skills.id"), nullable=False, index=True)
    path = Column(String(512), nullable=False)
    content = Column(Text, nullable=False)
    checksum = Column(String(64), nullable=False)
    updated_at = Column(DateTime, default=dt.datetime.utcnow, nullable=False)

    skill = relationship("Skill", back_populates="files")


class ThreadSkillBinding(Base):
    __tablename__ = "thread_skill_bindings"
    __table_args__ = (
        UniqueConstraint("thread_id", "skill_id", name="uq_thread_skill_bindings_thread_skill"),
        UniqueConstraint("thread_id", "position", name="uq_thread_skill_bindings_thread_position"),
    )

    id = Column(String(36), primary_key=True, default=_uuid)
    thread_id = Column(String(36), ForeignKey("threads.id"), nullable=False, index=True)
    skill_id = Column(String(36), ForeignKey("skills.id"), nullable=False, index=True)
    position = Column(Integer, nullable=False)
    enabled = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=dt.datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=dt.datetime.utcnow, nullable=False)

    thread = relationship("Thread", back_populates="skill_bindings")
    skill = relationship("Skill", back_populates="thread_bindings")


class ThreadSkillMaterializationState(Base):
    __tablename__ = "thread_skill_materialization_state"

    thread_id = Column(String(36), ForeignKey("threads.id"), primary_key=True)
    desired_hash = Column(String(64), nullable=True)
    materialized_hash = Column(String(64), nullable=True)
    status = Column(String(16), default="ready", nullable=False)
    materialized_root = Column(String(1024), nullable=True)
    last_error = Column(Text, nullable=True)
    updated_at = Column(DateTime, default=dt.datetime.utcnow, nullable=False)

    thread = relationship("Thread", back_populates="skill_materialization_state")


class MCPServer(Base):
    __tablename__ = "mcp_servers"
    __table_args__ = (UniqueConstraint("user_id", "key", name="uq_mcp_servers_user_key"),)

    id = Column(String(36), primary_key=True, default=_uuid)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    key = Column(String(64), nullable=False)
    name = Column(String(128), nullable=False)
    description = Column(Text, nullable=False)
    transport = Column(String(32), nullable=False)
    config_json = Column("config", JSON, nullable=False)
    encrypted_secret_json = Column(Text, nullable=True)
    enabled = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=dt.datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=dt.datetime.utcnow, nullable=False)

    user = relationship("User", back_populates="mcp_servers")
    thread_bindings = relationship(
        "ThreadMCPBinding", back_populates="mcp_server", cascade="all, delete-orphan"
    )


class ThreadMCPBinding(Base):
    __tablename__ = "thread_mcp_bindings"
    __table_args__ = (
        UniqueConstraint("thread_id", "mcp_id", name="uq_thread_mcp_bindings_thread_mcp"),
        UniqueConstraint("thread_id", "position", name="uq_thread_mcp_bindings_thread_position"),
    )

    id = Column(String(36), primary_key=True, default=_uuid)
    thread_id = Column(String(36), ForeignKey("threads.id"), nullable=False, index=True)
    mcp_id = Column(String(36), ForeignKey("mcp_servers.id"), nullable=False, index=True)
    position = Column(Integer, nullable=False)
    enabled = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=dt.datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=dt.datetime.utcnow, nullable=False)

    thread = relationship("Thread", back_populates="mcp_bindings")
    mcp_server = relationship("MCPServer", back_populates="thread_bindings")


class ThreadMCPRuntimeState(Base):
    __tablename__ = "thread_mcp_runtime_state"

    thread_id = Column(String(36), ForeignKey("threads.id"), primary_key=True)
    status = Column(String(16), default="ready", nullable=False)
    last_error = Column(Text, nullable=True)
    updated_at = Column(DateTime, default=dt.datetime.utcnow, nullable=False)

    thread = relationship("Thread", back_populates="mcp_runtime_state")


# LangGraph checkpoint tables (MySQL)
class Checkpoint(Base):
    __tablename__ = "checkpoints"

    thread_id = Column(String(36), primary_key=True)
    checkpoint_ns = Column(String(255), primary_key=True, default="")
    checkpoint_id = Column(String(255), primary_key=True)
    parent_checkpoint_id = Column(String(255), nullable=True)
    type = Column(String(255), nullable=True)
    checkpoint = Column(Text, nullable=True)
    metadata_json = Column("metadata", Text, nullable=True)


class Write(Base):
    __tablename__ = "writes"

    thread_id = Column(String(36), primary_key=True)
    checkpoint_ns = Column(String(255), primary_key=True, default="")
    checkpoint_id = Column(String(255), primary_key=True)
    task_id = Column(String(255), primary_key=True)
    idx = Column(Integer, primary_key=True)
    channel = Column(String(255), nullable=False)
    type = Column(String(255), nullable=True)
    value = Column(Text, nullable=True)
