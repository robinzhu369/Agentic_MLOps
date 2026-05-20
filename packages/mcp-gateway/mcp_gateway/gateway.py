"""MCP Gateway — FastAPI application."""
# ruff: noqa: B008
from __future__ import annotations

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse

from .audit import AuditLogger
from .auth import AuthError, JWTAuthService
from .pii import PIIMasker
from .rbac import PermissionDeniedError, RBACService
from .registry import CapabilityRegistry
from .router import RoutingError, ToolRouter
from .schemas import (
    MCPServerRegistration,
    RefreshRequest,
    TokenRequest,
    ToolCallRequest,
    ToolCallResponse,
)

app = FastAPI(
    title="MCP Gateway",
    version="0.1.0",
    description=(
        "Unified gateway for MCP tool calls: "
        "auth, RBAC, routing, audit, PII masking"
    ),
)

# --- Singletons ---
_auth_service = JWTAuthService()
_rbac_service = RBACService()
_pii_masker = PIIMasker()
_audit_logger = AuditLogger(masker=_pii_masker)
_registry = CapabilityRegistry()
_router = ToolRouter(
    registry=_registry,
    rbac=_rbac_service,
    masker=_pii_masker,
    audit=_audit_logger,
)


# --- Dependencies ---


def get_current_user(
    authorization: str = Header(default=""),
) -> dict[str, str]:
    """Extract and verify JWT from Authorization header.

    Returns:
        Dict with 'user_id' and 'role'.
    """
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing Bearer token")

    token = authorization[7:]
    try:
        payload = _auth_service.verify_token(token)
    except AuthError as e:
        raise HTTPException(status_code=401, detail=e.message) from e

    return {"user_id": payload.sub, "role": payload.role}


# --- Auth Endpoints ---


@app.post("/auth/token")
async def login(request: TokenRequest) -> dict[str, str | int]:
    """Authenticate user and return token pair."""
    try:
        response = _auth_service.authenticate_user(
            request.username, request.password
        )
    except AuthError as e:
        raise HTTPException(status_code=401, detail=e.message) from e
    return response.model_dump()


@app.post("/auth/refresh")
async def refresh(request: RefreshRequest) -> dict[str, str | int]:
    """Refresh access token."""
    try:
        response = _auth_service.refresh_token(request.refresh_token)
    except AuthError as e:
        raise HTTPException(status_code=401, detail=e.message) from e
    return response.model_dump()


@app.post("/auth/revoke", status_code=204)
async def revoke(
    user: dict[str, str] = Depends(get_current_user),
    authorization: str = Header(default=""),
) -> None:
    """Revoke current token."""
    token = authorization[7:]
    payload = _auth_service.verify_token(token)
    _auth_service.revoke_token(payload.jti)


# --- MCP Endpoints ---


@app.get("/mcp/capabilities")
async def get_capabilities(
    user: dict[str, str] = Depends(get_current_user),
) -> dict[str, object]:
    """Get capability manifest with all available tools."""
    manifest = await _registry.get_manifest()
    return manifest.model_dump()


@app.post("/mcp/tools/call")
async def call_tool(
    request: ToolCallRequest,
    user: dict[str, str] = Depends(get_current_user),
) -> ToolCallResponse:
    """Execute a tool call through the gateway middleware chain."""
    try:
        response = await _router.route(
            request,
            user_id=user["user_id"],
            user_role=user["role"],
        )
    except PermissionDeniedError as e:
        raise HTTPException(
            status_code=403,
            detail={
                "error": "forbidden",
                "required_role": e.required_role.value,
                "tool_name": e.tool_name,
            },
        ) from e
    except RoutingError as e:
        raise HTTPException(
            status_code=e.status_code, detail=e.message
        ) from e

    return response


# --- Server Management ---


@app.post("/mcp/servers", status_code=201)
async def register_server(
    registration: MCPServerRegistration,
    user: dict[str, str] = Depends(get_current_user),
) -> dict[str, str]:
    """Register a new MCP Server."""
    if user["role"] != "admin":
        raise HTTPException(
            status_code=403, detail="Only admin can register servers"
        )
    await _registry.register_server(registration)
    return {"name": registration.name, "status": "registered"}


@app.delete("/mcp/servers/{name}", status_code=204)
async def deregister_server(
    name: str,
    user: dict[str, str] = Depends(get_current_user),
) -> None:
    """Deregister an MCP Server."""
    if user["role"] != "admin":
        raise HTTPException(
            status_code=403, detail="Only admin can deregister servers"
        )
    await _registry.deregister_server(name)


@app.get("/mcp/servers")
async def list_servers(
    user: dict[str, str] = Depends(get_current_user),
) -> list[dict[str, str]]:
    """List all registered MCP Servers."""
    servers = _registry.get_servers()
    return [s.model_dump() for s in servers]


# --- Health ---


@app.get("/health")
async def health() -> dict[str, str]:
    """Health check."""
    return {"status": "ok", "service": "mcp-gateway"}


# --- Error Handlers ---


@app.exception_handler(AuthError)
async def auth_error_handler(
    request: Request, exc: AuthError
) -> JSONResponse:
    """Handle authentication errors."""
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": "unauthorized", "detail": exc.message},
    )
