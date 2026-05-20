---
id: "F-06"
module: "feature-store"
title: "实时特征写入（流式）"
priority: P1
status: draft
owner: ""
dependencies: ["F-03"]
milestone: "W8"
---

# [F-06] 实时特征写入（流式）

## 概述

支持实时特征的流式写入，允许在线推理时将新产生的特征值直接写入 Redis 在线存储，无需等待批量物化。适用于需要实时更新的特征场景，如用户最近 N 笔交易的统计特征。通过 Feast 的 `push_to_online_store()` 接口实现，支持单条和批量写入。

## 验收标准

- [ ] AC-1: 单条特征写入延迟 <5ms（P99）
- [ ] AC-2: 批量写入（100 条）延迟 <50ms
- [ ] AC-3: 提供 `push_features` MCP Tool，Agent 可触发实时特征写入
- [ ] AC-4: 写入的特征立即可通过 `get_online_features()` 查询
- [ ] AC-5: 写入失败时返回明确错误，不静默丢失数据
- [ ] AC-6: 支持 `POST /api/feature-store/push` REST 接口，供外部系统调用

## 接口定义

```python
from pydantic import BaseModel
from typing import List, Dict, Any
import pandas as pd

class FeaturePushRequest(BaseModel):
    feature_view_name: str
    # 每条记录包含实体键和特征值
    records: List[Dict[str, Any]]
    # e.g. [{"transaction_id": 12345, "v1": -1.35, "amount": 149.62}]

class FeaturePushResponse(BaseModel):
    pushed_count: int
    failed_count: int
    latency_ms: float
    errors: List[str]

# MCP Tool 定义
PUSH_FEATURES_TOOL = {
    "name": "push_features",
    "description": "实时写入特征值到在线存储，立即可用于推理",
    "inputSchema": {
        "type": "object",
        "properties": {
            "feature_view_name": {"type": "string"},
            "records": {
                "type": "array",
                "items": {"type": "object"},
                "description": "特征记录列表，每条包含实体键和特征值"
            }
        },
        "required": ["feature_view_name", "records"]
    }
}

# 内部函数签名
def push_to_online_store(
    store: "FeatureStore",
    feature_view_name: str,
    df: pd.DataFrame,
) -> FeaturePushResponse: ...

# REST API
# POST /api/feature-store/push
#   Body: FeaturePushRequest
#   Response: 200 FeaturePushResponse
```

## 技术约束

- 使用 Feast 的 `store.push()` 方法（Feast 0.40+ 支持）
- 批量写入使用 Redis pipeline，减少网络往返
- 写入前验证特征视图存在且字段类型匹配
- 不支持写入离线存储（仅在线存储），离线数据通过 ETL 管道维护

## 测试策略

- 单元测试：FeaturePushRequest 验证；批量写入的 pipeline 构造
- 集成测试：写入 100 条特征 -> 立即查询 -> 验证返回值正确
- 性能测试：单条写入 P99 延迟；批量 100 条写入延迟

## 依赖关系

- 被阻塞：[F-03]
- 阻塞：[]

## 参考

- MVP_SPEC.md Section 3.5
- Feast Stream Ingestion: https://docs.feast.dev/reference/data-sources/push
