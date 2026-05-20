---
id: "U-03"
module: "web-ide"
title: "Notebook 视图"
priority: P0
status: draft
owner: ""
dependencies: ["U-02"]
milestone: "W6"
---

# [U-03] Notebook 视图

## 概述

在 Monaco 编辑器基础上提供 Jupyter Notebook 风格的 Cell 视图，支持代码 Cell 和 Markdown Cell 的创建、编辑和执行。Notebook 视图与代码编辑器共享左侧主区域，通过标签页或视图切换按钮在两种模式间切换。Cell 执行结果（输出、图表、错误）内联显示在 Cell 下方。

## 验收标准

- [ ] AC-1: 支持 Code Cell（Python）和 Markdown Cell 两种类型
- [ ] AC-2: `Cmd+Enter` 执行当前 Cell，执行结果内联显示（stdout、stderr、图表）
- [ ] AC-3: Cell 执行状态显示：空闲（○）、执行中（●动画）、成功（✓）、失败（✗）
- [ ] AC-4: 支持 Cell 的增加（上方/下方）、删除、上移/下移操作
- [ ] AC-5: Agent 生成的代码可通过"插入到 Notebook"按钮创建新 Cell 并填入代码
- [ ] AC-6: Notebook 文件以 `.ipynb` 格式保存，兼容标准 Jupyter 格式
- [ ] AC-7: Markdown Cell 支持实时预览（编辑时显示源码，失焦后渲染）
- [ ] AC-8: 执行输出支持富文本：纯文本、HTML 表格、matplotlib 图表（PNG）

## 接口定义

```typescript
// types/notebook.ts
interface NotebookCell {
  id: string;
  type: "code" | "markdown";
  source: string;
  outputs: CellOutput[];
  executionCount: number | null;
  metadata: Record<string, unknown>;
}

interface CellOutput {
  outputType: "stream" | "display_data" | "execute_result" | "error";
  text?: string;
  data?: {
    "text/plain"?: string;
    "text/html"?: string;
    "image/png"?: string;      // base64
  };
  ename?: string;              // 错误类型
  evalue?: string;             // 错误信息
  traceback?: string[];
}

interface Notebook {
  cells: NotebookCell[];
  metadata: {
    kernelspec: { name: string; display_name: string };
    language_info: { name: string; version: string };
  };
  nbformat: 4;
  nbformat_minor: 5;
}

// components/Notebook/NotebookView.tsx
interface NotebookViewProps {
  filePath: string;
  onInsertCell?: (code: string) => void;
}

// Kernel 通信（通过后端代理 Jupyter kernel）
// POST /api/kernel/execute  -> { output: CellOutput[], executionCount: number }
// POST /api/kernel/interrupt -> 204
// POST /api/kernel/restart  -> 204
```

## 技术约束

- Notebook 视图基于 Monaco Editor（U-02）的 Cell 封装，不引入独立的 Notebook 渲染库
- Kernel 执行通过后端代理（Python subprocess 或 Jupyter Server），不在浏览器端执行代码
- 图表渲染：matplotlib 输出以 PNG base64 格式传输，在 `<img>` 标签中显示
- `.ipynb` 文件读写通过 `/api/files` 接口，JSON 格式
- Cell ID 使用 UUID v4，保证唯一性
- 执行超时：单 Cell 默认 60s，超时后自动中断并显示错误

## 测试策略

- 单元测试：Notebook 序列化/反序列化（`.ipynb` JSON 格式）；Cell 增删移动操作
- 集成测试：执行 `print("hello")` Cell，验证输出显示 "hello"；执行错误代码，验证错误信息显示
- E2E（Playwright）：创建 Notebook -> 添加 Cell -> 执行 -> 验证输出 -> 保存 -> 重新打开验证持久化

## 依赖关系

- 被阻塞：[U-02]
- 阻塞：[]

## 参考

- MVP_SPEC.md Section 3.4
- Jupyter Notebook Format: https://nbformat.readthedocs.io/
