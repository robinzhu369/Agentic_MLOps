---
id: "G-05"
module: "mcp-gateway"
title: "结构化审计日志"
priority: P0
status: draft
owner: ""
dependencies: ["G-04"]
milestone: "W2"
---

# [G-05] 结构化审计日志

## 概述

记录所有经过 MCP Gateway 的工具调用的完整审计信息，包括调用者身份、工具名称、参数摘要、执行结果和耗时。审计日志以 JSON 结构化格式输出，支持后续安全审计、问题排查和使用分析。每条日志包含唯一 audit_id，与 trace_id 关联。

## 验收标准

- [ ] AC-1: 每次工具调用（成功或失败）在调用完成后 100ms 内写入审计日志，不阻塞响应返回
- [ ] AC-2: 审计日志包含必需字段：audit_id、trace_id、timestamp、user_id、session_id、tool_name、status、duration_ms、error_code（失败时）
- [ ] AC-3: 工具参数和响应内容经过 PII 脱敏（G-08）后才写入日志，禁止记录原始 PII 数据
- [ ] AC-4: 权限拒绝事件（G-03 返回 403）也必须记录审计日志，status 字段为 `permission_denied`
- [ ] AC-5: 审计日志写入失败不影响工具调用响应，失败时记录到系统错误日志并继续

## 接口定义

```python
from enum import Enum
from pydantic import BaseModel
from datetime import datetime
from typing import Any


class AuditStatus(str, Enum):
    SUCCESS = "success"
    FAILED = "failed"
    PERMISSION_DENIED = "permission_denied"
    CIRCUIT_OPEN = "circuit_open"
    DRY_RUN = "dry_run"


class AuditLogEntry(BaseModel):
    audit_id: str                        # UUID v4, unique per log entry
    trace_id: str                        # From G-04 routing
    timestamp: datetime
    user_id: str
    session_id: str
    tool_name: str
    arguments_summary: dict[str, Any]   # PII-masked arguments (not full args)
    status: AuditStatus
    duration_ms: int | None = None
    error_code: str | None = None
    error_message: str | None = None
    dry_run: bool = False


# JSON log line format (one JSON object per line):
# {
#   "audit_id": "uuid",
#   "trace_id": "uuid",
#   "timestamp": "2026-05-20T10:00:00Z",
#   "user_id": "user_123",
#   "session_id": "sess_456",
#   "tool_name": "jupyter.execute_code",
#   "arguments_summary": {"code_length": 150, "kernel_id": "k_789"},
#   "status": "success",
#   "duration_ms": 1234,
#   "dry_run": false
# }


class AuditLogger:
    def __init__(self, log_output: str = "stdout"):
        """
        Args:
            log_output: "stdout" | file path | "elasticsearch_url"
        """
        ...

    async def log(self, entry: AuditLogEntry) -> None:
        """
        Write audit log entry asynchronously.
        Never raises exceptions (errors go to system error log).
        """
        ...

    def _summarize_arguments(
        self,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Create a safe summary of arguments for logging.
        Replaces large values with size indicators, applies PII masking.
        E.g., {"code": "print('hello')"} -> {"code_length": 15}
        """
        ...
```

## 技术约束

- 日志格式：每行一个 JSON 对象（JSON Lines），使用 Python `structlog` 库
- 默认输出到 stdout，由容器日志收集器（如 Fluentd）转发到存储后端
- 审计日志写入使用 `asyncio.create_task` 异步执行，不 await，确保不阻塞响应
- arguments_summary 中禁止记录完整代码内容，只记录长度；禁止记录文件内容，只记录文件名
- audit_id 使用 UUID v4，与 trace_id 不同（trace_id 来自 G-04，audit_id 是日志专属 ID）

## 测试策略

- 单元测试：验证所有必需字段存在于日志输出；测试 arguments_summary 正确截断大字段；测试日志写入失败不抛出异常；测试 PII 数据不出现在日志中
- 集成测试：与 G-04 联调，验证每次工具调用产生对应审计日志；验证权限拒绝事件被记录
- E2E：执行完整 Agent 任务，通过日志文件验证所有工具调用均有对应审计记录

## 依赖关系

- 被阻塞：[G-04]
- 阻塞：[]

## 参考

- MVP_SPEC.md Section 3.2
