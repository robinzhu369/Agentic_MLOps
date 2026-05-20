---
id: "U-09"
module: "web-ide"
title: "文件浏览器"
priority: P0
status: draft
owner: ""
dependencies: ["U-01"]
milestone: "W6"
---

# [U-09] 文件浏览器

## 概述

Web-IDE 左侧的文件树浏览器，展示当前项目的目录结构，支持文件和目录的创建、重命名、删除操作。点击文件在编辑器（U-02）中打开，支持右键上下文菜单。文件浏览器与项目管理（U-01）联动，切换项目时自动更新文件树。

## 验收标准

- [ ] AC-1: 以树形结构展示项目目录，支持目录展开/折叠
- [ ] AC-2: 点击文件在编辑器（U-02）中打开，当前打开的文件高亮显示
- [ ] AC-3: 右键上下文菜单支持：新建文件、新建目录、重命名、删除（需确认）
- [ ] AC-4: 支持拖拽移动文件/目录（同项目内）
- [ ] AC-5: 文件图标根据扩展名显示（.py、.ipynb、.yaml、.md 等不同图标）
- [ ] AC-6: 切换项目时文件树自动刷新，展示新项目的目录结构
- [ ] AC-7: 文件树支持搜索（`Cmd+P` 快速打开文件，模糊匹配文件名）
- [ ] AC-8: 隐藏文件（以 `.` 开头）默认不显示，可通过设置切换

## 接口定义

```typescript
// types/filesystem.ts
interface FileNode {
  name: string;
  path: string;                // 相对于项目根目录的路径
  type: "file" | "directory";
  children?: FileNode[];       // 仅 directory 类型有此字段
  size?: number;               // 文件大小（bytes）
  modifiedAt?: string;
}

// components/Sidebar/FileExplorer.tsx
interface FileExplorerProps {
  projectId: string;
  onFileOpen: (filePath: string) => void;
  activeFilePath?: string;
}

// API
// GET  /api/files/tree?projectId={id}              -> FileNode (根节点)
// POST /api/files/create
//   Body: { projectId, path, type: "file"|"directory" }
// PUT  /api/files/rename
//   Body: { projectId, oldPath, newPath }
// DELETE /api/files?projectId={id}&path={path}
// PUT  /api/files/move
//   Body: { projectId, sourcePath, targetPath }
```

## 技术约束

- 文件树使用 `react-arborist` 或自定义递归组件实现，支持虚拟滚动（大目录性能）
- 文件操作通过后端 API 执行，不直接操作文件系统
- 快速打开（`Cmd+P`）使用模糊搜索库 `fuse.js`，搜索范围为当前项目所有文件
- 文件图标使用 `vscode-icons` 或 `file-icons` 图标集
- 目录展开状态存储在 localStorage，刷新后恢复
- 删除操作需二次确认（shadcn/ui AlertDialog）

## 测试策略

- 单元测试：FileNode 树形数据构建；文件路径规范化
- 集成测试：创建文件 -> 验证文件树出现新节点；删除文件 -> 验证节点消失
- E2E（Playwright）：右键新建文件 -> 输入文件名 -> 验证文件树和编辑器标签页更新

## 依赖关系

- 被阻塞：[U-01]
- 阻塞：[]

## 参考

- MVP_SPEC.md Section 3.4
