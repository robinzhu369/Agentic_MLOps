---
id: "A-06"
module: "agent-core"
title: "长期记忆（向量检索）"
priority: P0
status: draft
owner: ""
dependencies: ["A-05"]
milestone: "W7"
---

# [A-06] 长期记忆（向量检索）

## 概述

基于 pgvector 实现跨会话的长期记忆存储与语义检索。将重要的会话摘要、任务结果和用户偏好持久化为向量，支持在新会话中检索历史相关经验，为 A-07 Skill Library 提供底层存储能力。使用 bge-small-zh-v1.5 模型生成中文优化的语义向量。

## 验收标准

- [ ] AC-1: 会话结束时，系统自动将会话摘要（≤ 500 字）向量化并存入 pgvector，延迟 ≤ 2 秒
- [ ] AC-2: 语义检索 Top-K（默认 K=5）结果在 100 万条记录规模下 P99 延迟 ≤ 200ms
- [ ] AC-3: 相似度阈值（默认 0.75）以下的结果不返回，阈值可通过配置调整
- [ ] AC-4: 支持按 user_id 和 memory_type 过滤检索范围，不同用户数据严格隔离
- [ ] AC-5: 向量维度固定为 512（bge-small-zh-v1.5 输出维度），存储时验证维度一致性

## 接口定义

```python
from enum import Enum
from typing import Any
from pydantic import BaseModel
from datetime import datetime


class MemoryType(str, Enum):
    SESSION_SUMMARY = "session_summary"
    TASK_RESULT = "task_result"
    USER_PREFERENCE = "user_preference"
    SKILL = "skill"                       # Used by A-07


class MemoryEntry(BaseModel):
    memory_id: str
    user_id: str
    memory_type: MemoryType
    content: str                          # Human-readable text
    metadata: dict[str, Any] = {}        # e.g. {"session_id": ..., "task_type": ...}
    created_at: datetime


class MemorySearchResult(BaseModel):
    entry: MemoryEntry
    similarity: float                     # Cosine similarity [0, 1]


class LongTermMemory:
    def __init__(self, pg_dsn: str, embedding_model_path: str):
        ...

    async def store(
        self,
        user_id: str,
        memory_type: MemoryType,
        content: str,
        metadata: dict | None = None,
    ) -> str:
        """
        Embed content and store in pgvector.

        Returns:
            memory_id of the created entry.

        Raises:
            EmbeddingError: If embedding model fails.
            DimensionMismatchError: If embedding dimension != 512.
        """
        ...

    async def search(
        self,
        user_id: str,
        query: str,
        memory_type: MemoryType | None = None,
        top_k: int = 5,
        similarity_threshold: float = 0.75,
    ) -> list[MemorySearchResult]:
        """
        Semantic search over long-term memory using cosine similarity.

        Args:
            user_id: Restrict search to this user's memories.
            query: Natural language query string.
            memory_type: Optional filter by memory type.
            top_k: Maximum number of results.
            similarity_threshold: Minimum cosine similarity to include.

        Returns:
            List of MemorySearchResult sorted by similarity descending.
        """
        ...

    async def delete(self, memory_id: str, user_id: str) -> None:
        """Delete a memory entry. user_id required for ownership verification."""
        ...
```

## 技术约束

- 嵌入模型：`bge-small-zh-v1.5`，本地加载（不调用外部 API），使用 `sentence-transformers` 库
- 向量存储：PostgreSQL + pgvector 扩展，向量列类型 `vector(512)`，使用 IVFFlat 索引（lists=100）
- 数据库连接使用 `asyncpg` + 连接池，最大连接数 10
- 用户数据隔离通过 `user_id` 列的行级过滤实现，禁止跨用户查询
- 嵌入计算在 CPU 上运行，批量嵌入时 batch_size=32

## 测试策略

- 单元测试：mock pgvector 和嵌入模型，验证相似度阈值过滤逻辑；测试用户隔离（user_A 无法检索 user_B 数据）
- 集成测试：使用真实 pgvector 实例，插入 1000 条记录后验证检索延迟和准确率；测试维度不匹配时的错误处理
- E2E：完整会话结束→摘要存储→新会话检索历史经验的链路测试

## 依赖关系

- 被阻塞：[A-05]
- 阻塞：[A-07]

## 参考

- MVP_SPEC.md Section 3.1
