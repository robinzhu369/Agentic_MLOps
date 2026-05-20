---
id: "U-02"
module: "web-ide"
title: "代码编辑器（Monaco）"
priority: P0
status: draft
owner: ""
dependencies: []
milestone: "W6"
---

# [U-02] 代码编辑器（Monaco）

## 概述

集成 Monaco Editor（VS Code 同款编辑器内核）提供专业级代码编辑体验，支持 Python、SQL、YAML 等 MLOps 常用语言的语法高亮、自动补全和错误提示。编辑器占据 Web-IDE 左侧主区域，与右侧 Agent Chat 面板（U-04）并排显示，支持拖拽调整分栏比例。

## 验收标准

- [ ] AC-1: 支持 Python、SQL、YAML、JSON、Markdown 语法高亮
- [ ] AC-2: Python 代码自动补全（基于 Monaco 内置 IntelliSense）
- [ ] AC-3: 快捷键 `Cmd+K`（Mac）/`Ctrl+K`（Win）唤起 Agent Chat 面板并聚焦输入框
- [ ] AC-4: 快捷键 `Cmd+Enter` 执行当前 Notebook Cell（当 Notebook 视图激活时）
- [ ] AC-5: 编辑器与文件浏览器（U-09）联动：点击文件树中的文件，编辑器打开对应文件
- [ ] AC-6: 支持多标签页（Tab）同时打开多个文件，标签页显示文件名和修改状态（●）
- [ ] AC-7: 文件修改后自动保存（debounce 1s），或通过 `Cmd+S` 手动保存
- [ ] AC-8: Agent 生成代码后，用户点击"插入到编辑器"按钮，代码插入到当前光标位置

## 接口定义

```typescript
// components/Editor/MonacoEditor.tsx
interface MonacoEditorProps {
  filePath: string;
  language?: string;           // 自动检测或手动指定
  theme: "vs-dark" | "vs-light";
  onSave?: (content: string) => void;
  onCursorChange?: (position: { line: number; column: number }) => void;
}

// 编辑器实例暴露的方法（通过 ref）
interface EditorRef {
  insertText: (text: string, position?: "cursor" | "end") => void;
  getValue: () => string;
  setValue: (content: string) => void;
  focus: () => void;
  getSelection: () => string;
}

// 文件标签页状态
interface EditorTab {
  filePath: string;
  fileName: string;
  isDirty: boolean;            // 有未保存修改
  language: string;
}

// Zustand store
interface EditorStore {
  tabs: EditorTab[];
  activeTabPath: string | null;
  openFile: (filePath: string) => void;
  closeTab: (filePath: string) => void;
  markDirty: (filePath: string) => void;
}

// API
// GET  /api/files?path={filePath}   -> { content: string }
// PUT  /api/files?path={filePath}   -> { success: boolean }
```

## 技术约束

- 使用 `@monaco-editor/react` 包（版本 ≥4.6），不直接操作 Monaco AMD loader
- 编辑器主题跟随全局主题设置（U-10），通过 `monaco.editor.setTheme()` 切换
- 文件内容通过 Next.js API Route 读写，不直接访问文件系统（安全隔离）
- 编辑器实例通过 React ref 暴露，供 Agent Chat（U-04）调用 `insertText`
- 自动保存使用 `useDebounce` hook，防抖 1000ms
- 大文件（>1MB）显示警告，不加载到编辑器

## 测试策略

- 单元测试：EditorStore 的 openFile/closeTab/markDirty action
- 集成测试：打开 Python 文件，验证语法高亮正确；修改内容后验证 isDirty=true
- E2E（Playwright）：打开文件 -> 修改内容 -> 等待自动保存 -> 刷新页面 -> 验证内容持久化

## 依赖关系

- 被阻塞：[]
- 阻塞：[U-03]

## 参考

- MVP_SPEC.md Section 3.4
- Monaco Editor: https://microsoft.github.io/monaco-editor/
