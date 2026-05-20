---
id: "R-05"
module: "rag-engine"
title: "混合检索（向量+BM25）"
priority: P1
status: draft
owner: ""
dependencies: ["R-04"]
milestone: "W4"
---

# [R-05] 混合检索（向量+BM25）

## 概述

将 Qdrant 向量检索与 OpenSearch 2.x BM25 全文检索融合，通过 Reciprocal Rank Fusion（RRF）算法合并两路结果，提升检索命中率。混合检索相比纯向量检索，命中率应提升 ≥15%，特别适合包含专业术语、规则编号等精确匹配需求的合规和 AML 文档场景。

## 验收标准

- [ ] AC-1: 混合检索命中率（Hit Rate@10）相比纯向量检索提升 ≥15%（在测试集上验证）
- [ ] AC-2: OpenSearch 使用中文分词（IK Analyzer），正确处理中文专业术语
- [ ] AC-3: RRF 融合公式：`score = Σ 1/(k + rank_i)`，k=60
- [ ] AC-4: 混合检索端到端延迟 <200ms（两路并行执行）
- [ ] AC-5: `SearchRequest.retrieval_mode` 支持 `"vector"` | `"bm25"` | `"hybrid"`
- [ ] AC-6: OpenSearch 索引与 Qdrant collection 保持同步（文档增删时同步更新）
- [ ] AC-7: BM25 索引字段：`text`（中文分词）、`section_title`、`domain`

## 接口定义

```python
from pydantic import BaseModel
from typing import List, Literal, Optional

class RetrievalMode(str):
    VECTOR = "vector"
    BM25 = "bm25"
    HYBRID = "hybrid"

class SearchRequest(BaseModel):
    query: str
    top_k: int = 10
    score_threshold: float = 0.5
    domain: Optional[str] = None
    retrieval_mode: str = "hybrid"   # 新增字段
    rrf_k: int = 60                  # RRF 参数

class HybridSearchResult(BaseModel):
    chunk_id: str
    document_id: str
    text: str
    rrf_score: float
    vector_rank: Optional[int]
    bm25_rank: Optional[int]
    domain: str
    metadata: dict

# 内部函数签名
def bm25_search(
    query: str,
    index_name: str = "rag_chunks",
    top_k: int = 20,
    domain: Optional[str] = None,
) -> List[dict]: ...

def reciprocal_rank_fusion(
    vector_results: List[dict],
    bm25_results: List[dict],
    k: int = 60,
    top_k: int = 10,
) -> List[HybridSearchResult]: ...

def hybrid_search(
    query: str,
    top_k: int = 10,
    domain: Optional[str] = None,
    rrf_k: int = 60,
) -> "SearchResponse": ...

# OpenSearch 索引 mapping
# {
#   "mappings": {
#     "properties": {
#       "chunk_id": { "type": "keyword" },
#       "document_id": { "type": "keyword" },
#       "domain": { "type": "keyword" },
#       "text": {
#         "type": "text",
#         "analyzer": "ik_max_word",
#         "search_analyzer": "ik_smart"
#       },
#       "section_title": { "type": "text", "analyzer": "ik_smart" }
#     }
#   }
# }
```

## 技术约束

- OpenSearch 版本 2.x，通过 Docker 部署
- 中文分词插件：`analysis-ik`，版本与 OpenSearch 匹配
- 两路检索并行执行（asyncio.gather），不串行等待
- RRF 融合在应用层实现，不依赖 OpenSearch 的 hybrid search 功能
- OpenSearch HTTP 端口 9200，内存限制 2GB（`-Xms1g -Xmx1g`）
- 文档写入时同时更新 Qdrant 和 OpenSearch，使用事务性重试保证最终一致

## 测试策略

- 单元测试：构造已知排名的 vector_results 和 bm25_results，验证 RRF 融合结果顺序正确
- 集成测试：构建包含专业术语（如"反洗钱"、"KYC"）的测试集，对比 vector-only 和 hybrid 的 Hit Rate@10
- 性能测试：并发 10 个混合检索请求，验证 P95 延迟 <300ms

## 依赖关系

- 被阻塞：[R-04]
- 阻塞：[R-06]

## 参考

- MVP_SPEC.md Section 3.3
- RRF 论文: Cormack et al., "Reciprocal Rank Fusion outperforms Condorcet and individual Rank Learning Methods"
