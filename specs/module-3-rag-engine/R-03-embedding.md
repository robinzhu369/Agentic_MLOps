---
id: "R-03"
module: "rag-engine"
title: "Embedding 生成（bge-small-zh）"
priority: P0
status: draft
owner: ""
dependencies: ["R-02"]
milestone: "W4"
---

# [R-03] Embedding 生成（bge-small-zh）

## 概述

使用 BAAI/bge-small-zh-v1.5 模型将 Chunk 文本转换为稠密向量表示，并批量写入 Qdrant 向量数据库。bge-small-zh-v1.5 针对中文语义检索优化，输出 512 维向量，在资源占用和检索质量之间取得平衡，适合 MVP 阶段的本地部署。

## 验收标准

- [ ] AC-1: 使用 `BAAI/bge-small-zh-v1.5` 模型，输出向量维度为 512
- [ ] AC-2: 批量 Embedding 吞吐量满足整体 ≥100 chunks/sec 的要求（GPU 加速时）
- [ ] AC-3: Embedding 结果与 Chunk 元数据一起写入 Qdrant collection
- [ ] AC-4: 支持 CPU 降级运行（吞吐量可降低，但功能不受影响）
- [ ] AC-5: 模型首次加载后缓存至内存，避免重复加载
- [ ] AC-6: 向量写入 Qdrant 使用批量 upsert，批大小 ≥100
- [ ] AC-7: Qdrant collection 名称为 `rag_chunks`，距离度量为 Cosine

## 接口定义

```python
from pydantic import BaseModel
from typing import List
import numpy as np

class EmbeddingConfig(BaseModel):
    model_name: str = "BAAI/bge-small-zh-v1.5"
    batch_size: int = 128
    device: str = "auto"          # "auto" | "cpu" | "cuda" | "mps"
    normalize_embeddings: bool = True
    # bge 模型推荐在查询时加前缀
    query_instruction: str = "为这个句子生成表示以用于检索相关文章："
    passage_instruction: str = ""  # 文档侧不加前缀

class EmbeddingResult(BaseModel):
    chunk_id: str
    vector: List[float]           # 512 维
    model_version: str

# 核心函数签名
def embed_chunks(
    chunks: List["Chunk"],        # 来自 R-02
    config: EmbeddingConfig,
) -> List[EmbeddingResult]: ...

def embed_query(
    query: str,
    config: EmbeddingConfig,
) -> List[float]: ...             # 512 维向量

# Qdrant 写入
def upsert_to_qdrant(
    collection_name: str,
    embeddings: List[EmbeddingResult],
    chunks: List["Chunk"],
) -> int: ...                     # 返回写入数量

# Qdrant collection schema
# {
#   "collection_name": "rag_chunks",
#   "vectors": { "size": 512, "distance": "Cosine" },
#   "payload_schema": {
#     "document_id": "keyword",
#     "domain": "keyword",
#     "section_title": "text",
#     "chunk_index": "integer",
#     "text": "text"
#   }
# }
```

## 技术约束

- 模型通过 `sentence-transformers` 库加载，版本 ≥2.6
- Qdrant Python client 版本 ≥1.10
- GPU 环境：CUDA 11.8+ 或 MPS（Apple Silicon）
- CPU 环境：批大小自动降至 32 以控制内存
- 模型文件从 HuggingFace Hub 下载，支持离线缓存（`HF_HUB_OFFLINE=1`）
- 向量维度固定为 512，不支持运行时更改（更改需重建 collection）

## 测试策略

- 单元测试：对固定文本生成 Embedding，验证向量维度为 512，L2 范数约为 1.0（归一化后）
- 集成测试：批量 Embed 100 个 Chunk，验证写入 Qdrant 后 collection 点数正确
- 性能测试：在 CPU 环境下测量 100 chunks 的 Embedding 耗时，记录基准值

## 依赖关系

- 被阻塞：[R-02]
- 阻塞：[R-04, R-08]

## 参考

- MVP_SPEC.md Section 3.3
- BAAI/bge-small-zh-v1.5: https://huggingface.co/BAAI/bge-small-zh-v1.5
