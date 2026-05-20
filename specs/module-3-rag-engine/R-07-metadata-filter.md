---
id: "R-07"
module: "rag-engine"
title: "元数据过滤（按域）"
priority: P0
status: draft
owner: ""
dependencies: ["R-04"]
milestone: "W4"
---

# [R-07] 元数据过滤（按域）

## 概述

在向量检索和混合检索的基础上，支持按文档域（domain）和其他元数据字段进行预过滤，将检索范围限定在特定知识域内。例如，Agent 处理合规问题时只检索 `domain=compliance` 的文档，避免无关领域的噪声干扰。元数据过滤在 Qdrant 的 payload filter 层实现，不影响检索延迟。

## 验收标准

- [ ] AC-1: 支持按 `domain` 字段过滤，可选值：`compliance`、`aml`、`feature-template`、`general`
- [ ] AC-2: 支持多域组合过滤（OR 逻辑），如 `domain IN ["compliance", "aml"]`
- [ ] AC-3: 支持按 `document_id` 精确过滤（限定在特定文档内检索）
- [ ] AC-4: 过滤条件通过 `SearchRequest.filters` 字段传入，格式为 Qdrant Filter JSON
- [ ] AC-5: 元数据过滤不增加检索延迟（Qdrant payload index 预建）
- [ ] AC-6: `domain` 字段在 Qdrant 中建立 payload index（keyword 类型）
- [ ] AC-7: 过滤后结果为空时返回空列表，附带 `filter_applied: true` 标记

## 接口定义

```python
from pydantic import BaseModel
from typing import List, Optional, Union

class DomainFilter(BaseModel):
    domains: List[str]           # OR 逻辑
    # e.g. ["compliance", "aml"]

class MetadataFilter(BaseModel):
    domain: Optional[DomainFilter] = None
    document_ids: Optional[List[str]] = None  # 精确文档过滤
    # 扩展字段：支持任意 Qdrant payload filter
    raw_filter: Optional[dict] = None

class SearchRequest(BaseModel):
    query: str
    top_k: int = 10
    score_threshold: float = 0.5
    # 简化接口：直接传 domain 字符串
    domain: Optional[str] = None
    # 高级接口：完整过滤条件
    metadata_filter: Optional[MetadataFilter] = None
    retrieval_mode: str = "hybrid"
    use_reranker: bool = False

class SearchResponse(BaseModel):
    query: str
    results: List["SearchResult"]
    total_found: int
    latency_ms: float
    retrieval_type: str
    filter_applied: bool         # 新增字段

# Qdrant payload index 创建（初始化时执行）
# client.create_payload_index(
#     collection_name="rag_chunks",
#     field_name="domain",
#     field_schema=PayloadSchemaType.KEYWORD,
# )
# client.create_payload_index(
#     collection_name="rag_chunks",
#     field_name="document_id",
#     field_schema=PayloadSchemaType.KEYWORD,
# )

# Qdrant filter 构造示例
# Filter(
#     must=[
#         FieldCondition(
#             key="domain",
#             match=MatchAny(any=["compliance", "aml"])
#         )
#     ]
# )
```

## 技术约束

- Qdrant payload index 在 collection 初始化时创建，不在请求时动态创建
- `domain` 和 `document_id` 字段必须建立 keyword 类型 payload index
- 过滤逻辑在 Qdrant 服务端执行，不在应用层后过滤
- `SearchRequest.domain` 是 `metadata_filter.domain` 的语法糖，两者互斥时 `metadata_filter` 优先
- OpenSearch（BM25 路径）的过滤通过 `term`/`terms` query 实现，与 Qdrant 过滤保持语义一致

## 测试策略

- 单元测试：构造包含多个 domain 的 Chunk 集合，验证 domain 过滤后只返回目标域的结果
- 集成测试：预加载 compliance 和 aml 两个域的文档，执行带 domain 过滤的检索，验证结果不混域
- 边界测试：过滤条件匹配零结果时，验证返回空列表且 `filter_applied=true`

## 依赖关系

- 被阻塞：[R-04]
- 阻塞：[R-09]

## 参考

- MVP_SPEC.md Section 3.3
- Qdrant Payload Filtering: https://qdrant.tech/documentation/concepts/filtering/
