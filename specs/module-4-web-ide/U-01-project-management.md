---
id: "U-01"
module: "web-ide"
title: "项目管理（创建/切换）"
priority: P0
status: draft
owner: ""
dependencies: []
milestone: "W6"
---

# [U-01] 项目管理（创建/切换）

## 概述

提供项目的创建、列表展示和切换功能，作为 Web-IDE 的工作空间管理基础。每个项目对应一个独立的文件系统目录和 Agent 会话上下文，用户可在多个项目间切换而不丢失各自的工作状态。MVP 阶段支持单用户多项目管理。

## 验收标准

- [ ] AC-1: 用户可通过"新建项目"对话框创建项目，输入项目名称和描述
- [ ] AC-2: 项目列表页展示所有项目，显示名称、创建时间、最后修改时间
- [ ] AC-3: 切换项目时，文件浏览器（U-09）、编辑器（U-02）和 Agent Chat（U-04）状态同步更新
- [ ] AC-4: 项目元数据持久化存储，刷新页面后不丢失
- [ ] AC-5: 项目名称唯一性校验，重名时提示错误
- [ ] AC-6: 支持项目删除（需二次确认），删除后自动切换到其他项目
- [ ] AC-7: 当前活跃项目在 URL 中体现（如 `/projects/{project_id}`），支持直接链接访问

## 接口定义

```typescript
// types/project.ts
interface Project {
  id: string;
  name: string;
  description: string;
  createdAt: string;
  updatedAt: string;
  rootPath: string;        // 服务端文件系统路径
}

interface CreateProjectRequest {
  name: string;
  description?: string;
  template?: "blank" | "fraud-detection" | "aml-scoring";
}

// API routes (Next.js App Router)
// GET  /api/projects          -> Project[]
// POST /api/projects          -> Project
// GET  /api/projects/[id]     -> Project
// PUT  /api/projects/[id]     -> Project
// DELETE /api/projects/[id]   -> 204

// React component
interface ProjectSwitcherProps {
  currentProjectId: string;
  onProjectChange: (projectId: string) => void;
}

// Zustand store
interface ProjectStore {
  projects: Project[];
  currentProjectId: string | null;
  setCurrentProject: (id: string) => void;
  createProject: (req: CreateProjectRequest) => Promise<Project>;
  deleteProject: (id: string) => Promise<void>;
}
```

## 技术约束

- 框架：Next.js 14 App Router + TypeScript
- 状态管理：Zustand，项目列表和当前项目 ID 存储在全局 store
- 持久化：项目元数据存储在后端（PostgreSQL 或 SQLite），不依赖 localStorage
- URL 路由：`/projects/[id]` 动态路由，切换项目时使用 `router.push`
- 项目模板：MVP 阶段提供"空白项目"和"欺诈检测"两个模板

## 测试策略

- 单元测试：Zustand store 的 createProject/deleteProject action 逻辑
- 集成测试：通过 API 创建项目，验证列表接口返回新项目；删除项目后验证列表不含该项目
- E2E（Playwright）：创建项目 -> 切换项目 -> 验证 URL 和文件浏览器内容更新

## 依赖关系

- 被阻塞：[]
- 阻塞：[U-09]

## 参考

- MVP_SPEC.md Section 3.4
