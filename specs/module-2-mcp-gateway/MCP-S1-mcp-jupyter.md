---
id: "MCP-S1"
module: "mcp-gateway"
title: "mcp-jupyter Server"
priority: P0
status: draft
owner: ""
dependencies: ["G-01", "G-04"]
milestone: "W2"
---

# [MCP-S1] mcp-jupyter Server

## 概述

封装 Jupyter Kernel 操作为 MCP 标准工具，提供代码执行、Kernel 管理和变量检查能力。mcp-jupyter 是 Agent 执行数据分析和模型训练代码的核心工具，通过 MCP Gateway 路由，支持多 Kernel 并发管理。

## 验收标准

- [ ] AC-1: `list_tools()` 返回 4 个工具的完整 MCP Spec 描述，包含 name、description、inputSchema 字段
- [ ] AC-2: `execute_code` 在 Kernel 中执行代码并返回 stdout、stderr 和执行结果，超时 300 秒
- [ ] AC-3: `create_kernel` 创建新 Jupyter Kernel，返回 kernel_id，支持 python3 和 ir（R）两种 kernel 类型
- [ ] AC-4: `list_variables` 返回当前 Kernel 命名空间中的变量名、类型和形状（针对 numpy/pandas 对象）
- [ ] AC-5: `restart_kernel` 重启指定 Kernel 并清空命名空间，操作完成后返回确认
- [ ] AC-6: 所有错误响应符合 MCP Spec 错误格式，不暴露原始 Python 异常堆栈给调用方

## 接口定义

```python
from typing import Any
from pydantic import BaseModel


# MCP Spec: all tools implement list_tools() and call_tool()

class MCPJupyterServer:
    async def list_tools(self) -> list[dict]:
        """
        Return MCP tool descriptors for all 4 tools.

        Returns list of:
        {
            "name": str,
            "description": str,
            "inputSchema": {
                "type": "object",
                "properties": {...},
                "required": [...]
            }
        }
        """
        ...

    async def call_tool(
        self,
        name: str,
        arguments: dict[str, Any],
    ) -> dict:
        """
        Dispatch to the appropriate tool implementation.

        Returns MCP Spec response:
        {
            "content": [{"type": "text", "text": "..."}],
            "isError": bool
        }

        Raises:
            MCPToolNotFoundError: name not in ["execute_code", "create_kernel",
                                               "list_variables", "restart_kernel"]
        """
        ...


# Tool signatures:

async def execute_code(
    kernel_id: str,
    code: str,
    timeout_s: int = 300,
) -> dict:
    """
    Execute Python/R code in the specified Kernel.

    Returns:
        {
            "content": [{
                "type": "text",
                "text": JSON with keys: stdout, stderr, result, execution_count
            }]
        }
    """
    ...


async def create_kernel(
    kernel_type: str = "python3",
    session_id: str | None = None,
) -> dict:
    """
    Create a new Jupyter Kernel.

    Args:
        kernel_type: "python3" | "ir"
        session_id: Associate kernel with an Agent session for lifecycle management.

    Returns:
        {"content": [{"type": "text", "text": JSON with kernel_id, kernel_type, status}]}
    """
    ...


async def list_variables(kernel_id: str) -> dict:
    """
    List variables in Kernel namespace.

    Returns:
        {"content": [{"type": "text", "text": JSON array of {name, type, shape, preview}}]}
    """
    ...


async def restart_kernel(kernel_id: str) -> dict:
    """
    Restart Kernel and clear namespace.

    Returns:
        {"content": [{"type": "text", "text": "Kernel {kernel_id} restarted successfully"}]}
    """
    ...
```

## 技术约束

- 使用 `jupyter_client` 库与 Jupyter Server 通信，不直接管理 Kernel 进程
- Kernel 生命周期与 Agent 会话绑定，会话结束后 30 分钟自动关闭空闲 Kernel
- 代码执行超时通过 `jupyter_client` 的 `execute` 方法的 `timeout` 参数控制
- `list_variables` 通过执行 `%who_ls` magic 命令获取变量列表，再对每个变量执行类型检查
- 错误响应格式：`{"content": [{"type": "text", "text": "[ERROR] ..."}], "isError": true}`，不包含 Python traceback

## 测试策略

- 单元测试：mock jupyter_client，验证 list_tools() 返回正确 Schema；测试 execute_code 超时处理；测试错误响应格式合规
- 集成测试：连接真实 Jupyter Server，执行 Python 代码并验证输出；测试 Kernel 创建和重启；测试 list_variables 对 pandas DataFrame 返回正确 shape
- E2E：通过 MCP Gateway 调用 `jupyter.execute_code`，验证代码执行结果正确返回给 Agent

## 依赖关系

- 被阻塞：[G-01, G-04]
- 阻塞：[]

## 参考

- MVP_SPEC.md Section 3.2
- Anthropic MCP Specification
