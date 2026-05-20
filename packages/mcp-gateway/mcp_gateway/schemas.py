"""MCP Gateway — Pydantic schemas for requests, responses, and internal models."""
from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

# --- Auth ---


class TokenRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class RefreshRequest(BaseModel):
    refresh_token: str


class JWTPayload(BaseModel):
    sub: str  # user_id
    role: str  # "admin" | "scientist"
    exp: int
    iat: int
    jti: str


# --- RBAC ---


class Role(StrEnum):
    ADMIN = "admin"
    SCIENTIST = "scientist"


class ToolPermission(BaseModel):
    tool_name: str
    required_role: Role = Role.SCIENTIST


# --- Capability Manifest ---


class ToolSchema(BaseModel):
    tool_name: str  # "{server}.{tool}"
    description: str
    input_schema: dict[str, Any] = Field(default_factory=dict)
    server_name: str
    is_available: bool = True


class CapabilityManifest(BaseModel):
    tools: list[ToolSchema]
    generated_at: str  # ISO 8601
    server_count: int
    tool_count: int


class MCPServerRegistration(BaseModel):
    name: str
    base_url: str
    health_check_path: str = "/health"


# --- Tool Call ---


class ToolCallRequest(BaseModel):
    tool_name: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    session_id: str = ""
    dry_run: bool = False


class ToolCallResponse(BaseModel):
    tool_name: str
    content: list[dict[str, Any]]
    is_error: bool = False
    error_code: str | None = None
    error_message: str | None = None
    trace_id: str = ""
    duration_ms: int = 0


# --- Audit ---


class AuditStatus(StrEnum):
    SUCCESS = "success"
    FAILED = "failed"
    PERMISSION_DENIED = "permission_denied"
    CIRCUIT_OPEN = "circuit_open"
    DRY_RUN = "dry_run"


class AuditLogEntry(BaseModel):
    audit_id: str
    trace_id: str
    timestamp: datetime
    user_id: str
    session_id: str
    tool_name: str
    arguments_summary: dict[str, Any] = Field(default_factory=dict)
    status: AuditStatus
    duration_ms: int | None = None
    error_code: str | None = None
    error_message: str | None = None
    dry_run: bool = False
