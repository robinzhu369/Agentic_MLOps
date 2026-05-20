---
id: "F-03"
module: "feature-store"
title: "在线存储（Redis）"
priority: P0
status: draft
owner: ""
dependencies: ["F-01"]
milestone: "W5"
---

# [F-03] 在线存储（Redis）

## 概述

配置 Redis 作为 Feast 的在线特征存储，提供低延迟的实时特征查询服务。在线存储存储最新的特征值，供模型推理时使用。通过 Feast 的 `get_online_features()` 接口查询，要求单实体查询延迟 <10ms。在线存储的数据通过特征物化（F-05）从离线存储同步。

## 验收标准

- [ ] AC-1: Redis 7+ 通过 Docker Compose 部署，Feast 在线存储配置指向 Redis
- [ ] AC-2: `get_online_features()` 单实体查询延迟 <10ms（P99）
- [ ] AC-3: 物化后的特征可通过 `get_online_features()` 正确查询，返回值与离线存储一致
- [ ] AC-4: Redis 内存使用监控：物化 284,807 条记录后，内存占用 <2GB
- [ ] AC-5: 支持批量在线查询：一次查询最多 1000 个实体，延迟 <100ms
- [ ] AC-6: Redis 连接失败时，Feast 返回明确错误信息，不静默返回空值

## 接口定义

```python
from feast import FeatureStore
from typing import List

# 在线特征查询
def get_online_features(
    store: FeatureStore,
    entity_rows: List[dict],     # [{"transaction_id": 12345}, ...]
    feature_refs: List[str],     # ["fraud_features:v1", "fraud_features:amount", ...]
) -> dict:
    """
    返回:
    {
        "transaction_id": [12345],
        "fraud_features__v1": [-1.359807],
        "fraud_features__amount": [149.62],
        ...
    }
    """
    ...

# Redis 键格式（Feast 内部）
# feast:{project}:{feature_view}:{entity_key} -> Hash { feature_name: value, ... }

# 在线存储健康检查
def check_redis_connection(redis_url: str) -> bool: ...

# REST API（通过 MCP Tool 暴露，见 F-04）
# POST /api/feature-store/online/get
#   Body: { entity_rows: [...], feature_refs: [...] }
#   Response: { features: dict, latency_ms: float }
```

## 技术约束

- Redis 版本 7+，使用 `redis-py` 客户端（版本 ≥5.0）
- Feast 在线存储配置：`type: redis`，`connection_string: "redis:6379"`
- Redis 内存策略：`maxmemory-policy allkeys-lru`（LRU 淘汰，防止 OOM）
- 不启用 Redis 持久化（AOF/RDB），在线特征通过物化重建
- 连接池大小 ≥20，支持并发查询
- 批量查询使用 Redis pipeline 减少网络往返

## 测试策略

- 单元测试：在线特征查询结果格式验证；Redis 连接失败时的错误处理
- 集成测试：物化 100 条记录到 Redis，执行 `get_online_features()`，验证返回值与 PostgreSQL 中的原始数据一致
- 性能测试：并发 10 个查询，每次查询 100 个实体，验证 P99 延迟 <100ms

## 依赖关系

- 被阻塞：[F-01]
- 阻塞：[F-05, F-06]

## 参考

- MVP_SPEC.md Section 3.5
- Feast Redis Online Store: https://docs.feast.dev/reference/online-stores/redis
