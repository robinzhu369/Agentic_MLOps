---
id: "R-04"
module: "rag-engine"
title: "向量检索（Qdrant）"
priority: P0
status: draft
owner: ""
dependencies: ["R-03"]
milestone: "W4"
---

# [R-04] 向量检索（Qdrant）

## 概述

基于 Qdrant 1.10+ 实现高性能向量相似度检索，将用户查询转换为 Embedding 后在向量数据库中检索 Top-K 最相关 Chunk。该功能是 RAG 引擎的核心检索路径，要求 Top-10 检索延迟 <100ms，为 Agent 的上下文注入（R-09）提供基础。

## 验收标准

- [ ] AC-1: Top-10 向量检索端到端延迟 <100ms（含查询 Embedding 生成时间）
- [ ] AC-2: 支持 `POST /api/v1/rag/search` 接口，返回 Top-K 结果（K 默认 10，最大 50）
- [ ] AC-3: 每条检索结果包含：chunk_id、document_id、text、score、metadata
- [ ] AC-4: Qdrant 使用 HNSW 索引，`m=16, ef_construct=100`
- [ ] AC-5: 支持 `score_threshold` 参数过滤低相关性结果（默认 0.5）
- [ ] AC-6: 检索结果按相似度分数降序排列
- [ ] AC-7: 当 collection 为空时返回空列表，不报错

## 接口定义

```python
from pydantic import BaseModel
from typing import List, Optional

class SearchRequest(BaseModel):
    query: str
    top_k: int = 10              # 最大 50
    score_threshold: float = 0.5
    domain: Optional[str] = None  # 元数据过滤，见 R-07
    filters: Optional[dict] = None

class SearchResult(BaseModel):
    chunk_id: str
    document_id: str
    text: str
    score: float                 # Cosine 相似度，范围 [0, 1]
    section_title: Optional[str]
    domain: str
    metadata: dict

class SearchResponse(BaseModel):
    query: str
    results: List[SearchResult]
    total_found: int
    latency_ms: float
    retrieval_type: str = "vector"  # "vector" | "hybrid" | "reranked"

# REST API
# POST /api/v1/rag/search
#   Body: SearchRequest
#   Response: 200 SearchResponse

# 内部函数签名
def vector_search(
    query: str,
    collection_name: str = "rag_chunks",
    top_k: int = 10,
    score_threshold: float = 0.5,
    filters: Optional[dict] = None,
) -> SearchResponse: ...

# Qdrant HNSW 配置
# {
#   "hnsw_config": {
#     "m": 16,
#     "ef_construct": 100,
#     "full_scan_threshold": 10000
#   }
# }
```

## 技术约束

- Qdrant 版本 ≥1.10，通过 Docker 部署（`qdrant/qdrant:v1.10`）
- 查询 Embedding 复用 R-03 的 `embed_query()` 函数
- HNSW 参数：`m=16, ef_construct=100`，`ef`（查询时）=128
- Qdrant gRPC 端口 6334，HTTP 端口 6333
- 连接池大小 ≥10，支持并发检索
- 检索延迟监控通过 OpenTelemetry span 记录（见 NFR-01）

## 测试策略

- 单元测试：mock Qdrant client，验证查询参数构造正确（top_k、score_threshold、filters）
- 集成测试：预加载 1000 个 Chunk，执行 10 次检索，验证延迟 <100ms，结果按 score 降序
- 性能测试：并发 10 个检索请求，验证 P95 延迟 <200ms

## 依赖关系

- 被阻塞：[R-03]
- 阻塞：[R-05, R-07, R-09]

## 参考

- MVP_SPEC.md Section 3.3
- Qdrant HNSW 文档: https://qdrant.tech/documentation/concepts/indexing/
