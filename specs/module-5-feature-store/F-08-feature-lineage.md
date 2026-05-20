---
id: "F-08"
module: "feature-store"
title: "特征血缘"
priority: P1
status: draft
owner: ""
dependencies: ["F-04"]
milestone: "W8"
---

# [F-08] 特征血缘

## 概述

追踪特征从数据源到模型的完整血缘关系，记录特征视图的数据来源、转换逻辑、依赖的上游特征和使用该特征的下游模型。血缘信息通过 REST API 查询，并在 Web-IDE 侧边栏（U-08）中以有向图形式可视化展示，帮助用户理解特征的来源和影响范围。

## 验收标准

- [ ] AC-1: 特征视图注册时（F-04）自动记录血缘：数据源表、特征字段列表、注册时间
- [ ] AC-2: 模型训练时记录特征使用关系：哪个模型使用了哪些特征视图的哪些特征
- [ ] AC-3: 提供 `GET /api/feature-store/lineage/{feature_view}` 接口，返回上下游血缘图
- [ ] AC-4: 血缘图包含：数据源 -> 特征视图 -> 模型 的完整链路
- [ ] AC-5: 支持影响分析：查询"如果修改特征 X，哪些模型会受影响"
- [ ] AC-6: 血缘数据存储在 PostgreSQL，支持历史版本查询

## 接口定义

```python
from pydantic import BaseModel
from typing import List, Optional

class LineageNode(BaseModel):
    node_id: str
    node_type: str  # "data_source" | "feature_view" | "feature" | "model"
    name: str
    metadata: dict

class LineageEdge(BaseModel):
    source_id: str
    target_id: str
    edge_type: str  # "derives_from" | "used_by"
    metadata: dict

class LineageGraph(BaseModel):
    root_node: LineageNode
    nodes: List[LineageNode]
    edges: List[LineageEdge]

class ImpactAnalysis(BaseModel):
    feature_view: str
    affected_models: List[str]
    affected_feature_views: List[str]

# 内部函数签名
def record_feature_view_lineage(
    feature_view_name: str,
    source_table: str,
    features: List[str],
) -> None: ...

def record_model_feature_usage(
    model_name: str,
    model_version: str,
    feature_view_name: str,
    feature_names: List[str],
) -> None: ...

def get_lineage_graph(
    feature_view_name: str,
    depth: int = 3,              # 上下游追溯深度
) -> LineageGraph: ...

def get_impact_analysis(
    feature_view_name: str,
) -> ImpactAnalysis: ...

# REST API
# GET /api/feature-store/lineage/{feature_view}         -> LineageGraph
# GET /api/feature-store/lineage/{feature_view}/impact  -> ImpactAnalysis
```

## 技术约束

- 血缘数据存储在 PostgreSQL 的 `feature_lineage` 表（图结构用邻接表表示）
- 血缘记录在特征视图注册（F-04）和模型训练完成时自动触发，不需要手动调用
- 图遍历使用递归 CTE（PostgreSQL WITH RECURSIVE），不引入图数据库
- MVP 阶段血缘图可视化在前端使用 `react-flow` 库渲染（U-08 侧边栏）

## 测试策略

- 单元测试：血缘图构建（节点和边的正确性）；影响分析查询
- 集成测试：注册特征视图 -> 训练模型 -> 查询血缘图，验证完整链路
- 边界测试：循环依赖检测（特征视图 A 依赖 B，B 依赖 A）

## 依赖关系

- 被阻塞：[F-04]
- 阻塞：[]

## 参考

- MVP_SPEC.md Section 3.5
