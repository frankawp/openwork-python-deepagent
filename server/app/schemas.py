from __future__ import annotations

import datetime as dt
from typing import Any, Literal, Optional

from pydantic import BaseModel, EmailStr


class UserCreate(BaseModel):
    username: str
    email: EmailStr
    password: str
    is_admin: bool = False


class UserOut(BaseModel):
    id: str
    username: str
    email: EmailStr
    is_admin: bool


class AuthTokens(BaseModel):
    access_token: str
    refresh_token: str


class LoginPayload(BaseModel):
    email: EmailStr
    password: str


class ThreadOut(BaseModel):
    thread_id: str
    user_id: str
    status: str
    title: Optional[str] = None
    metadata: Optional[dict[str, Any]] = None
    thread_values: Optional[dict[str, Any]] = None
    created_at: dt.datetime
    updated_at: dt.datetime


class ThreadCreate(BaseModel):
    title: Optional[str] = None
    metadata: Optional[dict[str, Any]] = None


class ThreadUpdate(BaseModel):
    title: Optional[str] = None
    status: Optional[str] = None
    metadata: Optional[dict[str, Any]] = None
    thread_values: Optional[dict[str, Any]] = None


class SkillCreate(BaseModel):
    key: str
    name: str
    description: str
    enabled: bool = True


class SkillUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    enabled: Optional[bool] = None


class SkillOut(BaseModel):
    id: str
    user_id: str
    key: str
    name: str
    description: str
    enabled: bool
    created_at: dt.datetime
    updated_at: dt.datetime


class SkillFileUpsert(BaseModel):
    path: str
    content: str


class SkillFileOut(BaseModel):
    id: str
    skill_id: str
    path: str
    checksum: str
    updated_at: dt.datetime


class SkillFileDetailOut(SkillFileOut):
    content: str


MCPTransport = Literal["streamable_http", "sse", "stdio"]


class MCPServerCreate(BaseModel):
    key: str
    name: str
    description: str
    transport: MCPTransport
    config: dict[str, Any]
    secret: Optional[dict[str, Any]] = None
    enabled: bool = True


class MCPServerUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    transport: Optional[MCPTransport] = None
    config: Optional[dict[str, Any]] = None
    secret: Optional[dict[str, Any]] = None
    enabled: Optional[bool] = None


class MCPServerOut(BaseModel):
    id: str
    user_id: str
    key: str
    name: str
    description: str
    transport: MCPTransport
    config: dict[str, Any]
    has_secret: bool = False
    enabled: bool
    created_at: dt.datetime
    updated_at: dt.datetime


class MCPServerTestOut(BaseModel):
    success: bool
    message: str
    tool_count: int = 0
    tools: list[str] = []


class MCPServerTestIn(BaseModel):
    thread_id: Optional[str] = None


class ProviderOut(BaseModel):
    id: str
    name: str
    hasApiKey: bool


class ModelConfigOut(BaseModel):
    id: str
    name: str
    provider: str
    model: str
    description: Optional[str] = None
    available: bool


class ApiKeyIn(BaseModel):
    provider: str
    apiKey: str


class AgentStreamRequest(BaseModel):
    thread_id: str
    message: str
    model_id: Optional[str] = None
    command: Optional[dict[str, Any]] = None
    skills_enabled: bool = True


class AgentInterruptRequest(BaseModel):
    thread_id: str
    decision: dict[str, Any]
    model_id: Optional[str] = None
    skills_enabled: bool = True


class AgentCancelRequest(BaseModel):
    thread_id: str


class WorkspaceFile(BaseModel):
    path: str
    is_dir: bool
    size: Optional[int] = None
    modified_at: Optional[str] = None


class WorkspaceListOut(BaseModel):
    success: bool
    files: list[WorkspaceFile]
    workspacePath: Optional[str] = None
    error: Optional[str] = None


class WorkspaceTreeOut(BaseModel):
    success: bool
    path: str
    depth: int
    files: list[WorkspaceFile]
    workspacePath: Optional[str] = None
    error: Optional[str] = None


class WorkspaceReadOut(BaseModel):
    success: bool
    content: Optional[str] = None
    size: Optional[int] = None
    modified_at: Optional[str] = None
    error: Optional[str] = None
