---
id: "F-01"
module: "feature-store"
title: "Feast 部署与初始化"
priority: P0
status: draft
owner: ""
dependencies: []
milestone: "W5"
---

# [F-01] Feast 部署与初始化

## 概述

完成 Feast 0.40+ 的部署和初始化配置，建立特征存储的基础设施。包括 Feast 服务的 Docker 化部署、`feature_store.yaml` 配置文件编写、离线存储（PostgreSQL）和在线存储（Redis）的连接配置，以及 Feast 注册表的初始化。这是 Feature Store 模块所有功能的基础依赖。

## 验收标准

- [ ] AC-1: Feast 0.40+ 通过 Docker Compose 部署，`feast version` 命令返回正确版本
- [ ] AC-2: `feature_store.yaml` 配置完成，指定 PostgreSQL 为离线存储、Redis 为在线存储
- [ ] AC-3: `feast apply` 命令执行成功，注册表初始化无错误
- [ ] AC-4: Feast UI（`feast ui`）可通过浏览器访问（端口 8888）
- [ ] AC-5: 提供健康检查接口，验证 Feast 服务、PostgreSQL 和 Redis 连接均正常
- [ ] AC-6: 初始化脚本可幂等执行（重复运行不报错）
- [ ] AC-7: 欺诈检测数据集（Kaggle Credit Card Fraud，284,807 条）预加载到 PostgreSQL 离线存储

## 接口定义

```python
# feature_store.yaml 配置模板
FEATURE_STORE_CONFIG = """
project: agentic_mlops
registry: data/registry.db
provider: local
offline_store:
    type: postgres
    host: ${POSTGRES_HOST}
    port: 5432
    database: feast
    db_schema: public
    user: ${POSTGRES_USER}
    password: ${POSTGRES_PASSWORD}
online_store:
    type: redis
    connection_string: "${REDIS_HOST}:6379"
entity_key_serialization_version: 2
"""

# 初始化脚本签名
def initialize_feast_store(
    config_path: str = "feature_store.yaml",
    force_reinit: bool = False,
) -> bool:
    """
    初始化 Feast 注册表和存储后端。
    force_reinit=True 时清空现有注册表重新初始化。
    """
    ...

def health_check() -> dict:
    """
    返回各组件健康状态。
    {
        "feast": "ok" | "error",
        "postgres": "ok" | "error",
        "redis": "ok" | "error",
        "message": str
    }
    """
    ...

# REST API
# GET /api/feature-store/health  -> health_check() 结果
```

## 技术约束

- Feast 版本：0.40+，通过 `pip install feast[postgres,redis]` 安装
- PostgreSQL 版本：14+，数据库名 `feast`
- Redis 版本：7+，无密码（开发环境）
- Feast 注册表使用本地文件（`data/registry.db`），MVP 阶段不使用远程注册表
- Docker Compose 服务名：`feast`、`postgres`、`redis`
- 欺诈检测数据集加载脚本：`scripts/load_fraud_dataset.py`

## 测试策略

- 单元测试：`feature_store.yaml` 配置解析；health_check 各组件状态判断
- 集成测试：在 Docker Compose 环境中执行 `feast apply`，验证注册表文件生成；执行 health_check，验证三个组件均返回 "ok"
- E2E：完整 Docker Compose 启动后，验证 Feast UI 可访问，数据集已加载

## 依赖关系

- 被阻塞：[]
- 阻塞：[F-02, F-03, F-04, F-05]

## 参考

- MVP_SPEC.md Section 3.5
- Feast 文档: https://docs.feast.dev/
- Kaggle Credit Card Fraud: https://www.kaggle.com/datasets/mlg-ulb/creditcardfraud
