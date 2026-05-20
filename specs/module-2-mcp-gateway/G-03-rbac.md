---
id: "G-03"
module: "mcp-gateway"
title: "基础 RBAC（admin / scientist）"
priority: P0
status: draft
owner: ""
dependencies: ["G-02"]
milestone: "W2"
---

# [G-03] 基础 RBAC（admin / scientist）

## 概述

基于 JWT 中的 role 字段实现两级角色访问控制：admin 拥有全部权限，scientist 只能调用数据读取和模型训练类工具，不能执行系统管理操作。RBAC 在 MCP Gateway 层统一执行，下游 MCP Server 无需重复实现权限逻辑。

## 验收标准

- [ ] AC-1: scientist 角色调用 admin-only 工具时，Gateway 返回 HTTP 403，响应体包含 `{"error": "forbidden", "required_role": "admin"}`
- [ ] AC-2: admin 角色可调用所有工具，包括 scientist 可用工具
- [ ] AC-3: 工具权限配置存储于配置文件（YAML），支持热重载（无需重启服务）
- [ ] AC-4: 权限检查在 JWT 验证（G-02）之后、工具路由（G-04）之前执行，拒绝请求不产生审计日志中的工具调用记录（但记录权限拒绝事件）
- [ ] AC-5: 新注册的 MCP Server 工具默认权限为 scientist 可用，需管理员显式提升为 admin-only

## 接口定义

```python
from enum import Enum
from pydantic import BaseModel
from typing import Callable
from fastapi import Request


class Role(str, Enum):
    ADMIN = "admin"
    SCIENTIST = "scientist"


class ToolPermission(BaseModel):
    tool_name: str                       # e.g. "jupyter.execute_code"
    required_role: Role = Role.SCIENTIST # Minimum role required


class RBACConfig(BaseModel):
    tool_permissions: list[ToolPermission]
    default_role: Role = Role.SCIENTIST  # For unspecified tools


# Permission configuration file: config/rbac.yaml
# Example:
# tool_permissions:
#   - tool_name: "jupyter.restart_kernel"
#     required_role: admin
#   - tool_name: "mcp_data_catalog.profile_column"
#     required_role: scientist
# default_role: scientist


class RBACMiddleware:
    def __init__(self, config_path: str):
        ...

    async def check_permission(
        self,
        tool_name: str,
        user_role: Role,
    ) -> None:
        """
        Verify user role meets tool's required_role.

        Raises:
            PermissionDeniedError: User role insufficient for tool.
        """
        ...

    async def reload_config(self) -> None:
        """Hot-reload RBAC config from YAML file without service restart."""
        ...


def require_role(minimum_role: Role) -> Callable:
    """
    FastAPI dependency for route-level role enforcement.

    Usage:
        @router.post("/admin/servers")
        async def register_server(user=Depends(require_role(Role.ADMIN))):
            ...
    """
    ...
```

## 技术约束

- RBAC 配置文件路径通过环境变量 `RBAC_CONFIG_PATH` 指定，默认 `config/rbac.yaml`
- 热重载使用 `watchfiles` 库监听配置文件变更，变更后重新加载并记录日志
- 权限检查逻辑为纯内存操作，不访问数据库，延迟 < 1ms
- admin-only 工具列表初始包含：所有 `restart_*`、`delete_*`、`deploy_*` 前缀工具，以及 MCP Server 注册/注销接口
- 禁止在代码中硬编码权限规则，所有规则必须在配置文件中定义

## 测试策略

- 单元测试：验证 scientist 调用 admin-only 工具返回 403；验证 admin 调用所有工具通过；测试默认权限（未配置工具）为 scientist 可用；测试配置热重载
- 集成测试：与 G-02 联调，验证完整 JWT→RBAC 检查链路；测试权限拒绝事件记录到审计日志
- E2E：使用 scientist Token 尝试调用 admin-only 工具，验证 403 响应

## 依赖关系

- 被阻塞：[G-02]
- 阻塞：[]

## 参考

- MVP_SPEC.md Section 3.2
