"""Tests for MCP Gateway — auth, RBAC, PII, routing, audit."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from mcp_gateway.auth import AuthError, JWTAuthService
from mcp_gateway.gateway import app
from mcp_gateway.pii import PIIMasker, _luhn_check
from mcp_gateway.rbac import PermissionDeniedError, RBACService
from mcp_gateway.schemas import (
    Role,
    ToolCallResponse,
    ToolPermission,
)

# --- Auth Tests ---


class TestJWTAuth:
    def setup_method(self) -> None:
        self.service = JWTAuthService()

    def test_create_token_pair(self) -> None:
        response = self.service.create_token_pair("user1", "scientist")
        assert response.access_token
        assert response.refresh_token
        assert response.token_type == "bearer"
        assert response.expires_in == 3600

    def test_verify_valid_token(self) -> None:
        response = self.service.create_token_pair("user1", "admin")
        payload = self.service.verify_token(response.access_token)
        assert payload.sub == "user1"
        assert payload.role == "admin"
        assert payload.jti

    def test_verify_invalid_token(self) -> None:
        with pytest.raises(AuthError, match="Invalid token"):
            self.service.verify_token("invalid.token.here")

    def test_revoke_token(self) -> None:
        response = self.service.create_token_pair("user1", "scientist")
        payload = self.service.verify_token(response.access_token)
        self.service.revoke_token(payload.jti)
        with pytest.raises(AuthError, match="revoked"):
            self.service.verify_token(response.access_token)

    def test_refresh_token(self) -> None:
        original = self.service.create_token_pair("user1", "scientist")
        new_response = self.service.refresh_token(original.refresh_token)
        assert new_response.access_token != original.access_token

    def test_refresh_with_access_token_fails(self) -> None:
        response = self.service.create_token_pair("user1", "scientist")
        with pytest.raises(AuthError, match="Not a refresh token"):
            self.service.refresh_token(response.access_token)

    def test_authenticate_valid_user(self) -> None:
        response = self.service.authenticate_user("admin", "admin123")
        assert response.access_token
        payload = self.service.verify_token(response.access_token)
        assert payload.role == "admin"

    def test_authenticate_invalid_user(self) -> None:
        with pytest.raises(AuthError, match="Invalid credentials"):
            self.service.authenticate_user("admin", "wrong")


# --- RBAC Tests ---


class TestRBAC:
    def setup_method(self) -> None:
        self.rbac = RBACService(
            tool_permissions=[
                ToolPermission(
                    tool_name="jupyter.delete_kernel",
                    required_role=Role.ADMIN,
                ),
            ]
        )

    def test_scientist_can_access_default_tool(self) -> None:
        # Should not raise
        self.rbac.check_permission("jupyter.execute_code", "scientist")

    def test_scientist_cannot_access_admin_tool(self) -> None:
        with pytest.raises(PermissionDeniedError):
            self.rbac.check_permission("jupyter.delete_kernel", "scientist")

    def test_admin_can_access_admin_tool(self) -> None:
        self.rbac.check_permission("jupyter.delete_kernel", "admin")

    def test_admin_can_access_scientist_tool(self) -> None:
        self.rbac.check_permission("jupyter.execute_code", "admin")

    def test_get_accessible_tools(self) -> None:
        tools = ["jupyter.execute_code", "jupyter.delete_kernel"]
        accessible = self.rbac.get_accessible_tools("scientist", tools)
        assert "jupyter.execute_code" in accessible
        assert "jupyter.delete_kernel" not in accessible


# --- PII Tests ---


class TestPII:
    def setup_method(self) -> None:
        self.masker = PIIMasker()

    def test_mask_chinese_id(self) -> None:
        text = "用户身份证号: 110101199003071234"
        masked, count = self.masker.mask_string(text)
        assert "[ID_MASKED]" in masked
        assert "110101199003071234" not in masked
        assert count == 1

    def test_mask_bank_card_luhn_valid(self) -> None:
        # 4111111111111111 is a well-known Luhn-valid test number
        text = "卡号: 4111111111111111"
        masked, count = self.masker.mask_string(text)
        assert "[CARD_MASKED]" in masked
        assert count == 1

    def test_no_mask_non_luhn_number(self) -> None:
        text = "随机数字: 1234567890123456"
        masked, count = self.masker.mask_string(text)
        # 1234567890123456 fails Luhn, should not be masked
        assert count == 0

    def test_mask_dict_recursive(self) -> None:
        data = {
            "user": {"id_card": "110101199003071234"},
            "amount": 100.5,
        }
        masked, count = self.masker.mask_dict(data)
        assert masked["user"]["id_card"] == "[ID_MASKED]"
        assert masked["amount"] == 100.5
        assert count == 1

    def test_mask_response(self) -> None:
        response = ToolCallResponse(
            tool_name="test",
            content=[{"type": "text", "text": "ID: 110101199003071234"}],
            trace_id="t1",
        )
        masked = self.masker.mask_response(response)
        assert "[ID_MASKED]" in masked.content[0]["text"]

    def test_luhn_check(self) -> None:
        assert _luhn_check("4111111111111111") is True
        assert _luhn_check("1234567890123456") is False


# --- Gateway Integration Tests ---


class TestGatewayAPI:
    def setup_method(self) -> None:
        self.client = TestClient(app)

    def test_health(self) -> None:
        resp = self.client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    def test_login_success(self) -> None:
        resp = self.client.post(
            "/auth/token",
            json={"username": "admin", "password": "admin123"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data
        assert "refresh_token" in data

    def test_login_failure(self) -> None:
        resp = self.client.post(
            "/auth/token",
            json={"username": "admin", "password": "wrong"},
        )
        assert resp.status_code == 401

    def test_protected_endpoint_no_token(self) -> None:
        resp = self.client.get("/mcp/capabilities")
        assert resp.status_code == 401

    def test_protected_endpoint_with_token(self) -> None:
        # Login first
        login_resp = self.client.post(
            "/auth/token",
            json={"username": "scientist", "password": "sci123"},
        )
        token = login_resp.json()["access_token"]

        resp = self.client.get(
            "/mcp/capabilities",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "tools" in data
        assert "tool_count" in data

    def test_register_server_admin_only(self) -> None:
        # Scientist cannot register
        login_resp = self.client.post(
            "/auth/token",
            json={"username": "scientist", "password": "sci123"},
        )
        token = login_resp.json()["access_token"]

        resp = self.client.post(
            "/mcp/servers",
            json={
                "name": "jupyter",
                "base_url": "http://localhost:9000",
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 403

    def test_register_server_as_admin(self) -> None:
        login_resp = self.client.post(
            "/auth/token",
            json={"username": "admin", "password": "admin123"},
        )
        token = login_resp.json()["access_token"]

        resp = self.client.post(
            "/mcp/servers",
            json={
                "name": "jupyter",
                "base_url": "http://localhost:9000",
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 201
        assert resp.json()["status"] == "registered"

    def test_tool_call_rbac_denied(self) -> None:
        from mcp_gateway.gateway import _rbac_service

        _rbac_service.set_permission("admin_tool.delete", Role.ADMIN)

        login_resp = self.client.post(
            "/auth/token",
            json={"username": "scientist", "password": "sci123"},
        )
        token = login_resp.json()["access_token"]

        resp = self.client.post(
            "/mcp/tools/call",
            json={
                "tool_name": "admin_tool.delete",
                "arguments": {},
                "session_id": "s1",
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 403
        assert resp.json()["detail"]["error"] == "forbidden"

    def test_tool_call_no_server(self) -> None:
        login_resp = self.client.post(
            "/auth/token",
            json={"username": "admin", "password": "admin123"},
        )
        token = login_resp.json()["access_token"]

        resp = self.client.post(
            "/mcp/tools/call",
            json={
                "tool_name": "nonexistent.tool",
                "arguments": {},
                "session_id": "s1",
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 502
