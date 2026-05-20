---
id: "G-02"
module: "mcp-gateway"
title: "统一认证（JWT）"
priority: P0
status: draft
owner: ""
dependencies: []
milestone: "W2"
---

# [G-02] 统一认证（JWT）

## 概述

MCP Gateway 的所有 API 端点（除健康检查外）均要求有效 JWT Bearer Token。Gateway 负责 Token 签发、验证和刷新，下游 MCP Server 无需独立实现认证逻辑，统一由 Gateway 代理认证。

## 验收标准

- [ ] AC-1: `POST /auth/token` 接受 username/password，验证通过后返回 access_token（TTL 1 小时）和 refresh_token（TTL 7 天）
- [ ] AC-2: 所有受保护端点在收到无效或过期 JWT 时返回 HTTP 401，响应体包含 `{"error": "unauthorized", "message": "..."}`
- [ ] AC-3: `POST /auth/refresh` 接受有效 refresh_token，返回新 access_token，旧 access_token 立即失效
- [ ] AC-4: JWT Payload 必须包含 `sub`（user_id）、`role`（admin/scientist）、`exp`、`iat`、`jti`（唯一 ID，用于吊销）字段
- [ ] AC-5: Token 吊销通过 Redis 黑名单实现，吊销后的 jti 在 TTL 内拒绝访问

## 接口定义

```python
from pydantic import BaseModel


class TokenRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int                      # Seconds until access_token expiry


class RefreshRequest(BaseModel):
    refresh_token: str


class JWTPayload(BaseModel):
    sub: str                             # user_id
    role: str                            # "admin" | "scientist"
    exp: int                             # Unix timestamp
    iat: int                             # Unix timestamp
    jti: str                             # UUID, unique per token


# REST API
# POST /auth/token    (body: TokenRequest)   -> TokenResponse
# POST /auth/refresh  (body: RefreshRequest) -> TokenResponse
# POST /auth/revoke   (header: Authorization: Bearer <token>) -> 204


class JWTAuthService:
    def __init__(self, secret_key: str, redis_client):
        ...

    def create_token_pair(
        self,
        user_id: str,
        role: str,
    ) -> TokenResponse:
        """Issue access_token (1h) and refresh_token (7d)."""
        ...

    async def verify_token(self, token: str) -> JWTPayload:
        """
        Verify JWT signature, expiry, and blacklist status.

        Raises:
            AuthError: Token invalid, expired, or revoked.
        """
        ...

    async def refresh_token(self, refresh_token: str) -> TokenResponse:
        """
        Issue new access_token from valid refresh_token.
        Revokes old access_token's jti.
        """
        ...

    async def revoke_token(self, jti: str, ttl_seconds: int) -> None:
        """Add jti to Redis blacklist with remaining TTL."""
        ...
```

## 技术约束

- JWT 签名算法：HS256，密钥从环境变量 `JWT_SECRET_KEY` 读取（最小 32 字节）
- 使用 `python-jose[cryptography]` 库处理 JWT 操作
- 密码存储使用 bcrypt（cost factor 12），禁止明文或 MD5/SHA1 存储
- Token 黑名单 Redis Key 格式：`auth:revoked:{jti}`，TTL 与 Token 剩余有效期一致
- FastAPI 依赖注入：`Depends(get_current_user)` 用于所有受保护路由

## 测试策略

- 单元测试：验证 Token 签发包含所有必需字段；测试过期 Token 返回 401；测试吊销后的 Token 被拒绝；测试 bcrypt 密码验证
- 集成测试：完整登录→使用 Token→刷新→吊销流程；验证 Redis 黑名单正确设置 TTL
- E2E：Agent Core（A-04）使用 Token 调用 MCP Gateway，验证认证链路正常

## 依赖关系

- 被阻塞：[]
- 阻塞：[G-03]

## 参考

- MVP_SPEC.md Section 3.2
