---
id: "U-08"
module: "web-ide"
title: "特征/模型列表侧边栏"
priority: P1
status: draft
owner: ""
dependencies: ["F-01"]
milestone: "W8"
---

# [U-08] 特征/模型列表侧边栏

## 概述

在 Web-IDE 左侧提供特征视图和已注册模型的快速浏览侧边栏，与文件浏览器（U-09）并列或通过标签页切换。用户可在侧边栏中查看 Feast 特征视图定义、特征统计信息和 MLflow 模型注册表，支持一键将特征视图代码插入到编辑器。

## 验收标准

- [ ] AC-1: 侧边栏显示 Feast 特征视图列表，每项显示：名称、特征数量、最后物化时间
- [ ] AC-2: 点击特征视图展开详情：特征列表（名称、类型）、数据源、TTL
- [ ] AC-3: "插入代码"按钮将特征视图的 Python 定义代码插入到当前编辑器光标位置
- [ ] AC-4: 侧边栏显示 MLflow 模型注册表，每项显示：模型名称、最新版本、状态（Staging/Production）
- [ ] AC-5: 侧边栏数据每 60s 自动刷新
- [ ] AC-6: 支持搜索过滤：在侧边栏顶部输入关键词，实时过滤特征视图和模型列表
- [ ] AC-7: 侧边栏宽度固定 280px，内容超出时垂直滚动

## 接口定义

```typescript
// types/feature-store.ts
interface FeatureView {
  name: string;
  features: Array<{ name: string; dtype: string }>;
  entities: string[];
  ttl: string;                 // e.g. "86400s"
  dataSource: string;
  lastMaterializationTime?: string;
  tags: Record<string, string>;
}

interface RegisteredModel {
  name: string;
  latestVersion: string;
  stage: "None" | "Staging" | "Production" | "Archived";
  description?: string;
  createdAt: string;
}

// components/Sidebar/FeatureModelSidebar.tsx
interface FeatureModelSidebarProps {
  projectId: string;
  onInsertCode: (code: string) => void;
}

// API
// GET /api/feature-views          -> FeatureView[]
// GET /api/feature-views/{name}/code  -> { code: string }  (Python 定义)
// GET /api/models                 -> RegisteredModel[]
```

## 技术约束

- 侧边栏使用 shadcn/ui 的 `Accordion` 组件展示特征视图详情
- 数据通过后端代理 Feast SDK 和 MLflow REST API
- 特征视图 Python 代码由后端根据 Feast 元数据动态生成
- 搜索过滤在前端实现（不发起新 API 请求），使用 `useMemo` 过滤列表
- 侧边栏与文件浏览器（U-09）通过标签页切换，共享同一侧边栏容器

## 测试策略

- 单元测试：特征视图列表过滤逻辑；代码生成格式验证
- 集成测试：mock Feast API，验证特征视图列表正确渲染；点击"插入代码"验证编辑器内容更新
- E2E（Playwright）：在侧边栏搜索"transaction" -> 验证过滤结果 -> 点击插入代码 -> 验证编辑器内容

## 依赖关系

- 被阻塞：[F-01]
- 阻塞：[]

## 参考

- MVP_SPEC.md Section 3.4, 3.5
