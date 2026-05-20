---
id: "R-02"
module: "rag-engine"
title: "Chunk 切分（章节+滑窗）"
priority: P0
status: draft
owner: ""
dependencies: ["R-01"]
milestone: "W4"
---

# [R-02] Chunk 切分（章节+滑窗）

## 概述

对解析后的文档文本执行智能切分，结合章节边界感知和滑动窗口两种策略，生成平均 500-800 字符的语义连贯 Chunk。章节感知切分优先在标题、段落等自然边界处断开；滑动窗口切分用于无明显结构的长文本，保证相邻 Chunk 之间有重叠以避免语义截断。

## 验收标准

- [ ] AC-1: 章节感知切分：在 H1-H3 标题处强制断开，生成的 Chunk 不跨越章节边界
- [ ] AC-2: 滑动窗口切分：窗口大小 800 字符，步长 400 字符（50% 重叠）
- [ ] AC-3: 平均 Chunk 长度在 500-800 字符范围内（按字符数统计，不含空白）
- [ ] AC-4: 每个 Chunk 携带元数据：document_id、chunk_index、section_title、char_start、char_end
- [ ] AC-5: 切分吞吐量满足整体 ≥100 chunks/sec 的要求
- [ ] AC-6: 代码块（``` 包裹）作为原子单元，不在代码块内部切分
- [ ] AC-7: 中文文本按字符计数，英文文本按 token 估算（1 token ≈ 4 chars）

## 接口定义

```python
from pydantic import BaseModel
from typing import List, Literal, Optional

class ChunkStrategy(str):
    SECTION = "section"      # 章节感知
    SLIDING_WINDOW = "sliding_window"  # 滑动窗口
    AUTO = "auto"            # 自动选择（有结构用 section，否则 sliding_window）

class ChunkConfig(BaseModel):
    strategy: str = "auto"
    max_chunk_size: int = 800    # 字符数
    min_chunk_size: int = 200
    overlap_size: int = 400      # 滑窗重叠字符数
    respect_code_blocks: bool = True

class Chunk(BaseModel):
    chunk_id: str            # f"{document_id}_{chunk_index}"
    document_id: str
    chunk_index: int
    text: str
    section_title: Optional[str]
    char_start: int
    char_end: int
    token_estimate: int
    metadata: dict           # 继承自文档元数据

class ChunkResult(BaseModel):
    document_id: str
    total_chunks: int
    avg_chunk_size: float
    chunks: List[Chunk]

# 内部函数签名
def chunk_document(
    document_id: str,
    text: str,
    structure: dict,         # 来自 R-01 解析器的 AST/结构信息
    config: ChunkConfig,
) -> ChunkResult: ...
```

## 技术约束

- 使用 `langchain_text_splitters.RecursiveCharacterTextSplitter` 作为基础，扩展章节感知逻辑
- 章节边界检测依赖 R-01 解析器输出的文档结构（标题层级信息）
- Chunk 元数据写入 Qdrant payload，支持后续元数据过滤（R-07）
- 切分结果缓存至内存队列，批量写入 Qdrant（批大小 100）
- 不依赖外部 LLM 进行切分决策，纯规则/统计方法

## 测试策略

- 单元测试：构造含多级标题的 Markdown 文本，验证章节边界切分正确；构造无结构长文本，验证滑窗重叠比例
- 集成测试：对真实 PDF 合规文档执行切分，统计 Chunk 长度分布，验证 95% 的 Chunk 在 200-1000 字符范围内
- E2E：文档接入后自动触发切分，验证 `GET /api/v1/rag/stats` 中 chunk_count 与预期一致

## 依赖关系

- 被阻塞：[R-01]
- 阻塞：[R-03]

## 参考

- MVP_SPEC.md Section 3.3
