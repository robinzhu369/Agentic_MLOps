---
id: "F-04"
module: "feature-store"
title: "特征视图注册（通过 MCP）"
priority: P0
status: draft
owner: ""
dependencies: ["F-01", "MCP-S2"]
milestone: "W5"
---

# [F-04] 特征视图注册（通过 MCP）

## 概述

通过 MCP Tool 暴露特征视图注册功能，允许 Agent 自动生成并注册 Feast 特征视图定义。Agent 根据用户需求（如"为欺诈检测创建包含 V1-V10 的特征视图"）自动生成 Python 特征视图代码，通过 `register_feature_view` MCP Tool 提交注册，无需用户手动编写 Feast 配置。

## 验收标准

- [ ] AC-1: `register_feature_view` MCP Tool 注册到 MCP Gateway，Agent 可调用
- [ ] AC-2: Agent 可通过自然语言描述生成特征视图定义，并通过 MCP Tool 注册
- [ ] AC-3: 注册成功后，`feast apply` 自动执行，特征视图在 Feast 注册表中可见
- [ ] AC-4: 注册失败时（如字段类型错误、重名冲突），返回明确错误信息
- [ ] AC-5: 支持特征视图的更新（覆盖注册）和删除
- [ ] AC-6: 注册的特征视图在 Web-IDE 侧边栏（U-08）中实时显示
- [ ] AC-7: 提供 `list_feature_views` MCP Tool，返回所有已注册特征视图的摘要

## 接口定义

```python
from pydantic import BaseModel
from typing import List, Optional

class FeatureField(BaseModel):
    name: str
    dtype: str  # "float32" | "float64" | "int32" | "int64" | "string" | "bool"

class FeatureViewDefinition(BaseModel):
    name: str
    entities: List[str]          # 实体名称列表，如 ["transaction"]
    features: List[FeatureField]
    source_table: str            # PostgreSQL 表名
    ttl_seconds: int = 86400     # 特征有效期
    tags: dict = {}
    description: str = ""

# MCP Tool 定义
REGISTER_FEATURE_VIEW_TOOL = {
    "name": "register_feature_view",
    "description": "注册 Feast 特征视图定义，使特征可用于训练和推理",
    "inputSchema": {
        "type": "object",
        "properties": {
            "definition": {
                "type": "object",
                "description": "特征视图定义，包含名称、实体、特征列表和数据源"
            }
        },
        "required": ["definition"]
    }
}

LIST_FEATURE_VIEWS_TOOL = {
    "name": "list_feature_views",
    "description": "列出所有已注册的 Feast 特征视图",
    "inputSchema": { "type": "object", "properties": {} }
}

# 内部函数签名
def register_feature_view(
    definition: FeatureViewDefinition,
    overwrite: bool = False,
) -> dict:
    """
    生成 Python 特征视图代码 -> 写入临时文件 -> 执行 feast apply
    返回: { "status": "success"|"failed", "feature_view_name": str, "message": str }
    """
    ...

def generate_feature_view_code(definition: FeatureViewDefinition) -> str:
    """生成 Feast Python 特征视图定义代码"""
    ...
```

## 技术约束

- MCP Tool 通过 MCP Gateway（M-01）注册，遵循 MCP 协议规范
- `feast apply` 通过 subprocess 执行，超时 30s
- 特征视图 Python 代码生成使用 Jinja2 模板，不使用字符串拼接
- 注册操作需要 HITL 确认（U-06），属于"feature_store_write"类型操作
- 特征视图名称唯一性由 Feast 注册表保证，重名时返回错误（除非 `overwrite=True`）

## 测试策略

- 单元测试：`generate_feature_view_code()` 生成的代码语法正确（通过 `ast.parse()` 验证）
- 集成测试：通过 MCP Tool 注册特征视图，验证 `feast list feature-views` 输出包含新视图
- E2E：Agent 接收"创建包含 V1-V5 和 Amount 的特征视图"指令 -> 生成代码 -> HITL 确认 -> 注册成功 -> 侧边栏显示新视图

## 依赖关系

- 被阻塞：[F-01, MCP-S2]
- 阻塞：[F-08]

## 参考

- MVP_SPEC.md Section 3.5
- Feast Feature View: https://docs.feast.dev/getting-started/concepts/feature-view
