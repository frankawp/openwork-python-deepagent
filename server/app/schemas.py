from __future__ import annotations

import datetime as dt
from typing import Any, Optional

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


class WorkspaceReadOut(BaseModel):
    success: bool
    content: Optional[str] = None
    size: Optional[int] = None
    modified_at: Optional[str] = None
    error: Optional[str] = None
