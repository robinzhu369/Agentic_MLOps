---
id: "F-02"
module: "feature-store"
title: "离线存储（PostgreSQL）"
priority: P0
status: draft
owner: ""
dependencies: ["F-01"]
milestone: "W5"
---

# [F-02] 离线存储（PostgreSQL）

## 概述

配置 PostgreSQL 作为 Feast 的离线特征存储，存储历史特征数据用于模型训练。离线存储承载 Kaggle 欺诈检测数据集（284,807 条交易记录，30 个特征），支持 Feast 的 `get_historical_features()` 接口进行时间点正确（point-in-time correct）的特征查询，生成训练样本。

## 验收标准

- [ ] AC-1: PostgreSQL 中创建 `fraud_transactions` 表，包含 V1-V28（PCA 特征）、Amount、Time、Class 字段
- [ ] AC-2: 欺诈检测数据集（284,807 条）成功加载到 PostgreSQL，加载时间 <5 分钟
- [ ] AC-3: `get_historical_features()` 调用成功，返回包含正确时间戳的特征 DataFrame
- [ ] AC-4: 支持单表 500 万行的查询性能，`get_historical_features()` 对 10 万条实体的查询 <60s
- [ ] AC-5: 离线存储表建立必要索引：`event_timestamp`、`entity_id`（transaction_id）
- [ ] AC-6: 提供数据统计接口：总行数、各特征的均值/标准差/缺失率

## 接口定义

```python
from feast import FeatureStore
from datetime import datetime
import pandas as pd

# 欺诈检测数据集 schema
FRAUD_TABLE_SCHEMA = """
CREATE TABLE IF NOT EXISTS fraud_transactions (
    transaction_id  BIGSERIAL PRIMARY KEY,
    event_timestamp TIMESTAMPTZ NOT NULL,
    created         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    -- PCA 特征（预匿名化）
    v1  FLOAT, v2  FLOAT, v3  FLOAT, v4  FLOAT, v5  FLOAT,
    v6  FLOAT, v7  FLOAT, v8  FLOAT, v9  FLOAT, v10 FLOAT,
    v11 FLOAT, v12 FLOAT, v13 FLOAT, v14 FLOAT, v15 FLOAT,
    v16 FLOAT, v17 FLOAT, v18 FLOAT, v19 FLOAT, v20 FLOAT,
    v21 FLOAT, v22 FLOAT, v23 FLOAT, v24 FLOAT, v25 FLOAT,
    v26 FLOAT, v27 FLOAT, v28 FLOAT,
    amount FLOAT NOT NULL,
    class  INTEGER NOT NULL  -- 0: 正常, 1: 欺诈
);
CREATE INDEX IF NOT EXISTS idx_fraud_event_ts ON fraud_transactions(event_timestamp);
"""

# Feast 离线特征查询
def get_training_data(
    store: FeatureStore,
    entity_df: pd.DataFrame,    # 包含 transaction_id 和 event_timestamp
    feature_refs: list[str],
) -> pd.DataFrame: ...

# 数据统计
def get_offline_stats(
    table_name: str = "fraud_transactions",
) -> dict:
    """
    返回:
    {
        "row_count": 284807,
        "fraud_count": 492,
        "fraud_rate": 0.00173,
        "feature_stats": {
            "v1": {"mean": ..., "std": ..., "null_rate": 0.0},
            ...
        }
    }
    """
    ...

# REST API
# GET /api/feature-store/offline/stats  -> get_offline_stats()
```

## 技术约束

- PostgreSQL 版本 14+，使用 `psycopg2` 或 `asyncpg` 连接
- 数据加载使用 `COPY` 命令（批量导入），不使用逐行 INSERT
- `event_timestamp` 字段使用 UTC 时区，Feast 时间点查询依赖此字段
- V1-V28 特征为 PCA 变换后的匿名化数据，不含原始交易信息
- 数据库连接池大小 ≥10（使用 SQLAlchemy connection pool）
- 单表 500 万行性能目标：通过分区表（按月分区）或适当索引实现

## 测试策略

- 单元测试：数据加载脚本的 CSV 解析和类型转换；统计计算逻辑
- 集成测试：加载 1000 条样本数据，执行 `get_historical_features()`，验证返回 DataFrame 的列和行数正确
- 性能测试：加载完整 284,807 条数据，测量加载时间；对 1 万条实体执行历史特征查询，测量延迟

## 依赖关系

- 被阻塞：[F-01]
- 阻塞：[F-05]

## 参考

- MVP_SPEC.md Section 3.5
- Feast Offline Store: https://docs.feast.dev/reference/offline-stores/postgres
