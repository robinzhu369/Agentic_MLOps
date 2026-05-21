---
id: "R-01"
module: "rag-engine"
title: "文档接入（PDF/Markdown/Wiki）"
priority: P0
status: done
owner: ""
dependencies: []
milestone: "W4"
---

# [R-01] 文档接入（PDF/Markdown/Wiki）

## 概述

实现多格式文档的统一接入管道，支持 PDF、Markdown 和 Wiki 页面的解析与预处理。该功能是 RAG 引擎的入口，负责将原始文档转换为结构化文本，为后续 Chunk 切分和 Embedding 生成提供标准化输入。MVP 阶段需预加载约 50 份合规文档、30 条 AML 规则和 100 个特征模板。

## 验收标准

- [ ] AC-1: 支持 PDF 文件解析，保留段落结构，正确提取表格和列表内容
- [ ] AC-2: 支持 Markdown 文件解析，保留标题层级（H1-H6）和代码块
- [ ] AC-3: 支持 Wiki 页面接入（通过 URL 或 API），自动抓取正文内容
- [ ] AC-4: 文档接入吞吐量 ≥100 chunks/sec（含解析+预处理）
- [ ] AC-5: 解析失败时返回结构化错误信息，不影响其他文档的处理
- [ ] AC-6: 每份文档生成唯一 document_id，支持幂等重传
- [ ] AC-7: 接口 `POST /api/v1/rag/documents` 返回 202 Accepted 并附带任务 ID
- [ ] AC-8: 预加载脚本可一次性导入 180+ 份文档（合规文档+AML规则+特征模板）

## 接口定义

```python
from pydantic import BaseModel, HttpUrl
from typing import Literal, Optional
from enum import Enum

class DocumentType(str, Enum):
    PDF = "pdf"
    MARKDOWN = "markdown"
    WIKI = "wiki"

class DocumentIngestRequest(BaseModel):
    source_type: DocumentType
    # 文件上传时为 None，URL 接入时填写
    url: Optional[HttpUrl] = None
    # 文档所属域，用于元数据过滤
    domain: str  # e.g. "compliance", "aml", "feature-template"
    metadata: dict = {}

class DocumentIngestResponse(BaseModel):
    document_id: str
    task_id: str
    status: Literal["accepted", "processing", "completed", "failed"]
    message: str

class DocumentRecord(BaseModel):
    document_id: str
    title: str
    source_type: DocumentType
    domain: str
    chunk_count: int
    created_at: str
    metadata: dict

# REST API
# POST /api/v1/rag/documents
#   Content-Type: multipart/form-data (文件上传) 或 application/json (URL)
#   Response: 202 DocumentIngestResponse
#
# DELETE /api/v1/rag/documents/{document_id}
#   Response: 204 No Content
#
# GET /api/v1/rag/stats
#   Response: { total_documents, total_chunks, domains: [...] }
```

## 技术约束

- PDF 解析使用 `pdfplumber` 或 `pymupdf`，优先保留段落边界
- Markdown 解析使用 `mistune` 或 `python-markdown`，保留 AST 结构
- Wiki 接入通过 Confluence REST API v2 或 MediaWiki API
- 文档元数据存储于 Qdrant payload，不单独维护文档数据库
- 单文档大小上限 50MB
- 异步处理：接口立即返回 task_id，通过轮询或 WebSocket 获取进度
- 文档 ID 使用 SHA-256(source_url + domain) 保证幂等性

## 测试策略

- 单元测试：针对 PDF/Markdown/Wiki 各解析器，覆盖正常文档、空文档、损坏文件三类场景
- 集成测试：上传真实合规文档（PDF），验证解析结果包含预期关键词
- E2E：通过 `POST /api/v1/rag/documents` 上传文件，轮询任务状态至 completed，验证 `GET /api/v1/rag/stats` 中 chunk_count 增加

## 依赖关系

- 被阻塞：[]
- 阻塞：[R-02, R-08]

## 参考

- MVP_SPEC.md Section 3.3
