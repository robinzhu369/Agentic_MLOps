---
id: "U-07"
module: "web-ide"
title: "实验对比看板"
priority: P1
status: draft
owner: ""
dependencies: ["U-04"]
milestone: "W8"
---

# [U-07] 实验对比看板

## 概述

提供 MLflow 实验结果的可视化对比看板，允许用户在 Web-IDE 内直接查看和对比多次模型训练实验的指标（AUC、KS、精确率、召回率等）。看板以表格和折线图形式展示实验历史，支持多实验并排对比，帮助用户快速识别最优模型配置。

## 验收标准

- [ ] AC-1: 展示 MLflow 实验列表，每行显示：实验名称、运行时间、主要指标（AUC、KS）、状态
- [ ] AC-2: 支持多选实验（最多 5 个）进行并排对比，对比视图显示所有指标的差异
- [ ] AC-3: 指标趋势折线图：X 轴为训练轮次（epoch/iteration），Y 轴为指标值
- [ ] AC-4: 支持按指标排序（升序/降序），快速找到最优实验
- [ ] AC-5: 点击实验行展开详情：超参数、数据集信息、Artifact 列表
- [ ] AC-6: 看板数据每 30s 自动刷新，或通过手动刷新按钮触发
- [ ] AC-7: 支持实验标签过滤（如按 `model_type`、`feature_version` 过滤）

## 接口定义

```typescript
// types/experiment.ts
interface Experiment {
  experimentId: string;
  name: string;
  status: "running" | "finished" | "failed";
  startTime: string;
  endTime?: string;
  metrics: Record<string, number>;   // { auc: 0.95, ks: 0.72, ... }
  params: Record<string, string>;    // 超参数
  tags: Record<string, string>;
  artifactUri: string;
}

interface ExperimentComparison {
  experiments: Experiment[];
  metricKeys: string[];              // 所有实验共有的指标键
  paramKeys: string[];               // 所有实验共有的超参数键
}

// components/Dashboard/ExperimentDashboard.tsx
interface ExperimentDashboardProps {
  projectId: string;
}

// API（代理 MLflow REST API）
// GET  /api/experiments?projectId={id}           -> Experiment[]
// GET  /api/experiments/compare?ids={id1,id2}    -> ExperimentComparison
// GET  /api/experiments/{id}/metrics/{key}       -> { steps: number[], values: number[] }
```

## 技术约束

- 图表使用 `recharts` 库（与 shadcn/ui 生态兼容）
- 数据通过后端代理 MLflow REST API，不直接从前端访问 MLflow
- 自动刷新使用 `useInterval` + SWR 的 `refreshInterval` 选项
- 表格使用 `@tanstack/react-table` 实现排序、过滤、多选
- 最多同时对比 5 个实验，超出时提示用户取消选择

## 测试策略

- 单元测试：实验列表排序逻辑；指标对比差值计算
- 集成测试：mock MLflow API，验证实验列表正确渲染；多选实验后验证对比视图显示
- E2E（Playwright）：在看板中选择 2 个实验 -> 点击对比 -> 验证对比表格显示两个实验的指标差异

## 依赖关系

- 被阻塞：[U-04]
- 阻塞：[]

## 参考

- MVP_SPEC.md Section 3.4
