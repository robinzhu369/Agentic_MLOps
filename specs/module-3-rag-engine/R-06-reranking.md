---
id: "R-06"
module: "rag-engine"
title: "Re-ranking（bge-reranker）"
priority: P1
status: draft
owner: ""
dependencies: ["R-05"]
milestone: "W4"
---

# [R-06] Re-ranking（bge-reranker）

## 概述

使用 BAAI/bge-reranker-base 对混合检索（R-05）返回的候选 Chunk 进行精排，通过交叉编码器（Cross-Encoder）计算查询与每个 Chunk 的精确相关性分数，重新排序后取 Top-K。Re-ranking 应将 NDCG@5 提升 ≥10%，显著改善 Agent 获取的上下文质量。

## 验收标准

- [ ] AC-1: 使用 `BAAI/bge-reranker-base` 模型，输出相关性分数范围 [0, 1]
- [ ] AC-2: NDCG@5 相比混合检索（无 re-ranking）提升 ≥10%（在标注测试集上验证）
- [ ] AC-3: Re-ranking 输入为混合检索 Top-20 候选，输出 Top-K（K 由调用方指定，默认 5）
- [ ] AC-4: Re-ranking 延迟 <300ms（对 20 个候选 Chunk）
- [ ] AC-5: `SearchRequest.use_reranker` 参数控制是否启用 re-ranking（默认 false，P1 阶段启用）
- [ ] AC-6: Re-ranking 分数与原始 RRF 分数均保留在响应中，便于调试
- [ ] AC-7: Re-ranker 模型与 Embedding 模型共享 GPU 资源，避免 OOM

## 接口定义

```python
from pydantic import BaseModel
from typing import List, Optional

class RerankRequest(BaseModel):
    query: str
    candidates: List[str]        # Chunk 文本列表
    top_k: int = 5

class RerankResult(BaseModel):
    index: int                   # 原始候选列表中的索引
    text: str
    rerank_score: float          # Cross-Encoder 输出，[0, 1]
    original_rrf_score: float

class SearchRequest(BaseModel):
    query: str
    top_k: int = 10
    score_threshold: float = 0.5
    domain: Optional[str] = None
    retrieval_mode: str = "hybrid"
    use_reranker: bool = False   # 新增字段
    rerank_top_k: int = 5        # re-ranking 后返回数量
    rerank_candidate_k: int = 20 # 送入 re-ranker 的候选数量

# 内部函数签名
def rerank(
    query: str,
    candidates: List["SearchResult"],
    top_k: int = 5,
    candidate_k: int = 20,
) -> List[RerankResult]: ...

# 完整检索流水线
# 1. hybrid_search(query, top_k=candidate_k)  -> 20 candidates
# 2. rerank(query, candidates, top_k=top_k)   -> 5 results
# 3. 返回 SearchResponse(retrieval_type="reranked")
```

## 技术约束

- 模型：`BAAI/bge-reranker-base`，通过 `sentence-transformers` 的 `CrossEncoder` 类加载
- Re-ranker 与 Embedding 模型分别加载，但共享同一 GPU 设备
- 批量推理：20 个候选一次性送入模型，不逐条推理
- 模型加载后常驻内存，不在请求间重复加载
- CPU 降级：在无 GPU 环境下自动使用 CPU，延迟可能超过 300ms（记录警告日志）
- Re-ranking 延迟通过 OpenTelemetry span 单独记录

## 测试策略

- 单元测试：构造 query + 20 个候选（含已知相关和不相关），验证 re-ranking 后相关 Chunk 排名靠前
- 集成测试：构建 50 条标注查询（query + 相关 chunk_id），计算 NDCG@5，与 hybrid-only 基线对比
- 性能测试：测量 20 候选 re-ranking 的 P95 延迟，CPU 和 GPU 环境分别记录

## 依赖关系

- 被阻塞：[R-05]
- 阻塞：[]

## 参考

- MVP_SPEC.md Section 3.3
- BAAI/bge-reranker-base: https://huggingface.co/BAAI/bge-reranker-base
