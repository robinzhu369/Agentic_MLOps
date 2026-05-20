---
id: "NFR-01"
module: "cross-cutting"
title: "可观测性（OpenTelemetry + Langfuse）"
priority: P0
status: draft
owner: ""
dependencies: []
milestone: "W1"
---

# [NFR-01] 可观测性（OpenTelemetry + Langfuse）

## 概述

建立全平台统一的可观测性基础设施，通过 OpenTelemetry 收集分布式追踪、指标和日志，通过 Langfuse 专门追踪 LLM 调用链路（token 消耗、延迟、提示词版本）。所有 LLM 调用、MCP 工具调用和关键业务操作均需接入追踪，支持端到端的请求链路分析和性能瓶颈定位。

## 验收标准

- [ ] AC-1: 所有 LLM 调用通过 Langfuse 记录：模型名称、输入 token 数、输出 token 数、延迟、提示词版本
- [ ] AC-2: 所有 MCP 工具调用通过 OpenTelemetry span 记录：工具名称、输入参数摘要、执行时间、成功/失败
- [ ] AC-3: Agent 首 token 延迟（TTFT）通过 OpenTelemetry 指标记录，P95 <2s
- [ ] AC-4: MCP 工具调用 P95 延迟 <500ms，通过 OpenTelemetry 指标监控
- [ ] AC-5: Langfuse UI 可通过浏览器访问（端口 3000），展示 LLM 调用历史和 token 消耗统计
- [ ] AC-6: OpenTelemetry Collector 通过 Docker Compose 部署，接收 OTLP 格式数据
- [ ] AC-7: 日志格式统一为 JSON，包含 trace_id 和 span_id，支持与 trace 关联
- [ ] AC-8: 支持 10 个并发会话的追踪，不丢失数据

## 接口定义

```python
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
import langfuse
from functools import wraps
from typing import Callable

# OpenTelemetry 初始化
def setup_telemetry(
    service_name: str,
    otlp_endpoint: str = "http://otel-collector:4317",
) -> trace.Tracer:
    """初始化 OpenTelemetry tracer，在服务启动时调用"""
    ...

# Langfuse 初始化
def setup_langfuse(
    public_key: str,
    secret_key: str,
    host: str = "http://langfuse:3000",
) -> langfuse.Langfuse:
    """初始化 Langfuse 客户端"""
    ...

# LLM 调用追踪装饰器
def trace_llm_call(
    model: str,
    prompt_name: str = "",
) -> Callable:
    """
    装饰器：自动记录 LLM 调用到 Langfuse
    记录: input_tokens, output_tokens, latency_ms, model, prompt_version
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            ...
        return wrapper
    return decorator

# MCP 工具调用追踪装饰器
def trace_mcp_tool(tool_name: str) -> Callable:
    """
    装饰器：自动记录 MCP 工具调用到 OpenTelemetry
    span 属性: tool.name, tool.input_summary, tool.status
    """
    ...

# 关键指标定义
METRICS = {
    "agent.ttft_ms": "Agent 首 token 延迟（毫秒）",
    "mcp.tool_call_duration_ms": "MCP 工具调用延迟（毫秒）",
    "llm.input_tokens": "LLM 输入 token 数",
    "llm.output_tokens": "LLM 输出 token 数",
    "rag.search_latency_ms": "RAG 检索延迟（毫秒）",
    "feature_store.query_latency_ms": "特征查询延迟（毫秒）",
}
```

## 技术约束

- OpenTelemetry SDK：`opentelemetry-sdk` + `opentelemetry-exporter-otlp-proto-grpc`，版本 ≥1.24
- Langfuse：版本 ≥2.0，通过 Docker Compose 自托管部署
- OpenTelemetry Collector：`otel/opentelemetry-collector-contrib:0.100.0`
- 追踪采样率：开发环境 100%，生产环境 10%（通过环境变量配置）
- 日志库：`structlog`，输出 JSON 格式，自动注入 trace_id
- Langfuse 数据库：PostgreSQL（与 Feature Store 共享实例，不同 schema）
- 所有服务通过环境变量配置 OTLP endpoint，不硬编码

## 测试策略

- 单元测试：`trace_llm_call` 装饰器验证（mock Langfuse，验证记录的字段正确）；`trace_mcp_tool` 装饰器验证
- 集成测试：发起一次完整 Agent 请求，验证 Langfuse UI 中出现对应的 trace；验证 OpenTelemetry span 包含正确属性
- 性能测试：追踪开销 <1ms（不影响正常请求延迟）

## 依赖关系

- 被阻塞：[]
- 阻塞：[]

## 参考

- MVP_SPEC.md Section 4（非功能需求）
- OpenTelemetry Python: https://opentelemetry.io/docs/languages/python/
- Langfuse: https://langfuse.com/docs
