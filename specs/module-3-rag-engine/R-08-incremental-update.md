---
id: "R-08"
module: "rag-engine"
title: "增量更新"
priority: P1
status: draft
owner: ""
dependencies: ["R-01", "R-03"]
milestone: "W4"
---

# [R-08] 增量更新

## 概述

支持对已接入文档的增量更新，包括文档内容变更时的重新 Embedding 和向量替换，以及新文档的追加接入。增量更新避免全量重建索引，只处理变更部分，保证知识库与源文档保持同步。适用于合规规则更新、特征模板修订等场景。

## 验收标准

- [ ] AC-1: 文档内容变更时，通过 `PUT /api/v1/rag/documents/{id}` 触发增量更新
- [ ] AC-2: 增量更新只重新处理变更文档，不影响其他文档的向量数据
- [ ] AC-3: 更新过程中旧版本向量仍可检索（先写新版本，再删旧版本）
- [ ] AC-4: 支持文档删除：`DELETE /api/v1/rag/documents/{id}` 同时删除 Qdrant 和 OpenSearch 中的对应数据
- [ ] AC-5: 文档版本通过 `content_hash`（SHA-256）检测变更，内容未变时跳过更新
- [ ] AC-6: 增量更新任务异步执行，接口立即返回 task_id
- [ ] AC-7: 支持批量更新：`POST /api/v1/rag/documents/batch-update`，接受文档 ID 列表

## 接口定义

```python
from pydantic import BaseModel
from typing import List, Optional, Literal

class DocumentUpdateRequest(BaseModel):
    # 文件重新上传或 URL 重新抓取
    source_type: str
    url: Optional[str] = None
    domain: Optional[str] = None  # 不传则保持原域
    metadata: Optional[dict] = None

class UpdateResult(BaseModel):
    document_id: str
    task_id: str
    status: Literal["accepted", "skipped", "failed"]
    # skipped 表示内容未变更
    reason: Optional[str] = None
    old_chunk_count: int
    new_chunk_count: Optional[int] = None

class BatchUpdateRequest(BaseModel):
    document_ids: List[str]
    force: bool = False          # True 时忽略 content_hash，强制重新处理

# REST API
# PUT  /api/v1/rag/documents/{document_id}
#   Body: DocumentUpdateRequest
#   Response: 202 UpdateResult
#
# DELETE /api/v1/rag/documents/{document_id}
#   Response: 204 No Content
#
# POST /api/v1/rag/documents/batch-update
#   Body: BatchUpdateRequest
#   Response: 202 { task_id, document_count }

# 内部更新流程
def incremental_update(
    document_id: str,
    new_content: str,
    new_metadata: dict,
    force: bool = False,
) -> UpdateResult:
    # 1. 计算 content_hash，与存储的 hash 对比
    # 2. 若未变更且 force=False，返回 status="skipped"
    # 3. 执行 R-01 解析 -> R-02 切分 -> R-03 Embedding
    # 4. Qdrant: upsert 新 Chunk（带新版本标记）
    # 5. OpenSearch: 删除旧文档，写入新文档
    # 6. Qdrant: 删除旧版本 Chunk
    ...
```

## 技术约束

- `content_hash` 存储在文档元数据中（Qdrant payload 或独立 KV 存储）
- 更新期间使用 `version` 字段区分新旧 Chunk，避免检索到混合版本
- 删除操作使用 Qdrant 的 `delete_vectors` + `delete_payload`，OpenSearch 的 `delete_by_query`
- 批量更新并发度 ≤5，避免压垮 Embedding 服务
- 更新任务状态持久化（Redis 或 PostgreSQL），支持查询历史更新记录

## 测试策略

- 单元测试：验证 content_hash 计算正确；验证内容未变时返回 skipped
- 集成测试：上传文档 -> 修改内容 -> 触发更新 -> 验证检索结果反映新内容
- 并发测试：同时触发同一文档的两次更新，验证最终状态一致（后写覆盖）

## 依赖关系

- 被阻塞：[R-01, R-03]
- 阻塞：[]

## 参考

- MVP_SPEC.md Section 3.3
