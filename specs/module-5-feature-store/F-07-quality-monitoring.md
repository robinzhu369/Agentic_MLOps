---
id: "F-07"
module: "feature-store"
title: "特征质量监控（IV/PSI）"
priority: P1
status: draft
owner: ""
dependencies: ["F-05"]
milestone: "W8"
---

# [F-07] 特征质量监控（IV/PSI）

## 概述

对已物化的特征进行质量监控，计算信息价值（IV）和群体稳定性指数（PSI）两个核心指标。IV 衡量特征对目标变量的预测能力，PSI 检测特征分布漂移。监控结果通过 REST API 和 Web-IDE 看板展示，当 PSI 超过阈值时触发告警。

## 验收标准

- [ ] AC-1: 计算所有特征视图中数值特征的 IV 值，IV>0.02 标记为"有预测价值"
- [ ] AC-2: 计算 PSI：以训练集分布为基准，对比当前在线特征分布，PSI>0.2 触发告警
- [ ] AC-3: 监控任务每日定时执行（UTC 00:00），结果持久化到 PostgreSQL
- [ ] AC-4: 提供 `GET /api/feature-store/quality` 接口，返回所有特征的 IV 和最新 PSI
- [ ] AC-5: PSI 超过 0.2 时，通过日志记录告警（MVP 阶段不发送邮件/Slack）
- [ ] AC-6: 支持手动触发质量检查：`POST /api/feature-store/quality/check`

## 接口定义

```python
from pydantic import BaseModel
from typing import List, Optional

class FeatureQualityMetrics(BaseModel):
    feature_name: str
    feature_view: str
    iv: float                    # 信息价值
    iv_label: str                # "无价值"(<0.02) | "弱"(0.02-0.1) | "中"(0.1-0.3) | "强"(>0.3)
    psi: Optional[float]         # 群体稳定性指数（需要基准分布）
    psi_status: Optional[str]    # "稳定"(<0.1) | "轻微漂移"(0.1-0.2) | "显著漂移"(>0.2)
    computed_at: str

class QualityReport(BaseModel):
    feature_view: str
    computed_at: str
    features: List[FeatureQualityMetrics]
    alert_count: int             # PSI > 0.2 的特征数量

# IV 计算（二分类）
def compute_iv(
    feature_values: list,
    target_values: list,         # 0/1 二分类标签
    bins: int = 10,
) -> float: ...

# PSI 计算
def compute_psi(
    baseline_values: list,       # 训练集分布
    current_values: list,        # 当前分布
    bins: int = 10,
) -> float: ...

# REST API
# GET  /api/feature-store/quality              -> QualityReport[]
# POST /api/feature-store/quality/check        -> 202 { task_id }
# GET  /api/feature-store/quality/{feature_view} -> QualityReport
```

## 技术约束

- IV 和 PSI 计算使用纯 Python + NumPy，不依赖外部统计库
- 基准分布（训练集）在首次物化时计算并存储到 PostgreSQL
- 监控任务使用 APScheduler 或 Celery Beat 定时执行
- 计算结果缓存 24 小时，避免重复计算
- 特征分箱（binning）使用等频分箱（quantile-based），处理偏态分布

## 测试策略

- 单元测试：IV 计算（已知输入验证输出）；PSI 计算（相同分布 PSI≈0，完全不同分布 PSI 较大）
- 集成测试：对欺诈检测数据集计算 V1-V28 的 IV，验证结果在合理范围内
- 告警测试：构造 PSI>0.2 的场景，验证告警日志记录

## 依赖关系

- 被阻塞：[F-05]
- 阻塞：[]

## 参考

- MVP_SPEC.md Section 3.5
- IV/PSI 计算方法: https://www.listendata.com/2015/03/weight-of-evidence-woe-and-information.html
