---
id: "R-09"
module: "rag-engine"
title: "Context 注入 Agent"
priority: P0
status: draft
owner: ""
dependencies: ["R-04", "A-02"]
milestone: "W4"
---

# [R-09] Context 注入 Agent

## 概述

将 RAG 检索结果注入 Agent 的系统提示或用户消息，为 Agent 提供领域知识上下文。该功能作为 MCP Tool 暴露给 Agent Core（A-02），Agent 在需要领域知识时调用 `rag_search` 工具，获取相关 Chunk 后自动构建上下文注入到 LLM 请求中。支持按域自动路由（合规问题 -> compliance 域，特征工程 -> feature-template 域）。

## 验收标准

- [ ] AC-1: `rag_search` MCP Tool 注册到 MCP Gateway，Agent 可通过标准 MCP 协议调用
- [ ] AC-2: Agent 调用 `rag_search` 后，返回的 Chunk 文本自动格式化为 `<context>` XML 标签注入提示
- [ ] AC-3: 支持域自动路由：根据查询内容自动选择 domain（可被显式参数覆盖）
- [ ] AC-4: Context 注入后的总 token 数不超过 LLM 上下文窗口的 50%（默认 4096 tokens）
- [ ] AC-5: 当检索结果为空时，Agent 收到明确提示"未找到相关文档"，不注入空上下文
- [ ] AC-6: 每次 `rag_search` 调用通过 OpenTelemetry 记录：query、domain、chunk_count、latency
- [ ] AC-7: 支持 `max_context_tokens` 参数控制注入的最大 token 数

## 接口定义

```python
from pydantic import BaseModel
from typing import List, Optional

# MCP Tool 定义（注册到 MCP Gateway）
RAG_SEARCH_TOOL = {
    "name": "rag_search",
    "description": (
        "在知识库中检索与查询相关的文档片段，用于回答合规、AML、特征工程等领域问题。"
        "返回格式化的上下文文本，可直接用于 LLM 提示。"
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "检索查询，使用自然语言描述需要了解的信息"
            },
            "domain": {
                "type": "string",
                "enum": ["compliance", "aml", "feature-template", "general", "auto"],
                "default": "auto",
                "description": "知识域，auto 时自动路由"
            },
            "top_k": {
                "type": "integer",
                "default": 5,
                "description": "返回的文档片段数量"
            },
            "max_context_tokens": {
                "type": "integer",
                "default": 4096,
                "description": "注入上下文的最大 token 数"
            }
        },
        "required": ["query"]
    }
}

class RagSearchToolInput(BaseModel):
    query: str
    domain: str = "auto"
    top_k: int = 5
    max_context_tokens: int = 4096

class RagSearchToolOutput(BaseModel):
    context: str                 # 格式化的上下文文本，注入 LLM 提示
    sources: List[dict]          # 来源信息：[{document_id, section_title, score}]
    chunk_count: int
    domain_used: str
    truncated: bool              # 是否因 token 限制被截断

# 上下文格式化模板
CONTEXT_TEMPLATE = """<context>
以下是从知识库检索到的相关文档片段，请参考这些信息回答问题：

{chunks}

来源：{sources}
</context>"""

# 域自动路由规则（关键词匹配）
DOMAIN_ROUTING_RULES = {
    "compliance": ["合规", "监管", "法规", "KYC", "AML", "反洗钱"],
    "aml": ["洗钱", "可疑交易", "风险评分", "黑名单"],
    "feature-template": ["特征", "feature", "特征工程", "特征视图"],
}

def route_domain(query: str) -> str:
    """根据查询内容自动选择 domain"""
    ...

def format_context(
    results: List["SearchResult"],
    max_tokens: int = 4096,
) -> RagSearchToolOutput: ...
```

## 技术约束

- `rag_search` 工具通过 MCP Gateway（M-01）注册，遵循 MCP 协议规范
- Token 计数使用 `tiktoken`（cl100k_base 编码）估算，不调用 LLM API
- 域自动路由使用关键词匹配，不调用 LLM（避免循环依赖）
- 上下文注入格式使用 XML 标签（`<context>`），与主流 LLM 提示工程最佳实践一致
- 每次工具调用的 Langfuse trace 包含：query、domain、retrieved_chunks、token_count

## 测试策略

- 单元测试：验证域自动路由规则；验证 token 截断逻辑（超出 max_context_tokens 时截断最后一个 Chunk）
- 集成测试：Agent 调用 `rag_search("什么是 KYC 要求")`，验证返回的 context 包含合规文档内容
- E2E：完整 Agent 对话流程，验证 Agent 在回答合规问题时自动调用 `rag_search` 并引用来源

## 依赖关系

- 被阻塞：[R-04, A-02]
- 阻塞：[]

## 参考

- MVP_SPEC.md Section 3.3
- MCP Tool 规范：Module 2 MCP Gateway
