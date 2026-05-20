---
id: "F-05"
module: "feature-store"
title: "特征物化（materialize）"
priority: P0
status: draft
owner: ""
dependencies: ["F-02", "F-03"]
milestone: "W5"
---

# [F-05] 特征物化（materialize）

## 概述

实现 Feast 特征物化流程，将离线存储（PostgreSQL）中的历史特征数据同步到在线存储（Redis），使特征可用于实时推理。支持全量物化（`feast materialize-incremental`）和增量物化，并通过 MCP Tool 暴露物化触发接口，允许 Agent 在模型训练完成后自动触发物化。

## 验收标准

- [ ] AC-1: `feast materialize-incremental` 命令执行成功，将最新特征同步到 Redis
- [ ] AC-2: 物化 284,807 条记录的完成时间 <10 分钟
- [ ] AC-3: 物化后，`get_online_features()` 返回的值与 PostgreSQL 中最新记录一致
- [ ] AC-4: 提供 `materialize_features` MCP Tool，Agent 可触发物化
- [ ] AC-5: 物化进度可查询：`GET /api/feature-store/materialize/status` 返回进度百分比
- [ ] AC-6: 物化失败时记录错误日志，不影响在线存储中已有的特征数据
- [ ] AC-7: 支持按特征视图名称选择性物化，不强制全量物化

## 接口定义

```python
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime

class MaterializeRequest(BaseModel):
    feature_view_names: Optional[List[str]] = None  # None 表示全部
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    # end_date 默认为当前时间

class MaterializeStatus(BaseModel):
    task_id: str
    status: str  # "running" | "completed" | "failed"
    progress_pct: float
    rows_processed: int
    total_rows: int
    started_at: str
    completed_at: Optional[str]
    error: Optional[str]

# MCP Tool 定义
MATERIALIZE_TOOL = {
    "name": "materialize_features",
    "description": "将离线特征存储中的数据物化到在线存储（Redis），使特征可用于实时推理",
    "inputSchema": {
        "type": "object",
        "properties": {
            "feature_view_names": {
                "type": "array",
                "items": {"type": "string"},
                "description": "要物化的特征视图名称列表，不传则物化所有视图"
            },
            "end_date": {
                "type": "string",
                "format": "date-time",
                "description": "物化截止时间，默认为当前时间"
            }
        }
    }
}

# 内部函数签名
def trigger_materialization(
    request: MaterializeRequest,
) -> str:  # 返回 task_id
    """异步触发物化，立即返回 task_id"""
    ...

def get_materialization_status(task_id: str) -> MaterializeStatus: ...

# REST API
# POST /api/feature-store/materialize
#   Body: MaterializeRequest
#   Response: 202 { task_id }
#
# GET /api/feature-store/materialize/status?task_id={id}
#   Response: MaterializeStatus
```

## 技术约束

- 物化通过 `feast materialize-incremental` CLI 命令执行（subprocess），或直接调用 Feast Python SDK
- 物化任务异步执行，状态存储在 Redis（`feast:materialize:task:{task_id}`）
- 增量物化使用 Feast 的 `last_updated_timestamp` 机制，只处理新增/变更数据
- 物化并发度：Feast 内部控制，不额外限制
- 物化操作需要 HITL 确认（U-06），属于"feature_store_write"类型

## 测试策略

- 单元测试：MaterializeRequest 参数验证；状态查询逻辑
- 集成测试：触发物化 -> 轮询状态至 completed -> 验证 Redis 中特征数量与 PostgreSQL 一致
- 性能测试：物化 284,807 条记录，测量完成时间，验证 <10 分钟

## 依赖关系

- 被阻塞：[F-02, F-03]
- 阻塞：[F-07]

## 参考

- MVP_SPEC.md Section 3.5
- Feast Materialization: https://docs.feast.dev/getting-started/concepts/feature-retrieval#online-feature-retrieval
