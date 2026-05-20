---
id: "U-04"
module: "web-ide"
title: "Agent Chat 面板"
priority: P0
status: draft
owner: ""
dependencies: ["A-10"]
milestone: "W6"
---

# [U-04] Agent Chat 面板

## 概述

Web-IDE 右侧的 Agent 对话面板，提供与 Agent Core 的实时交互界面。用户通过自然语言描述任务，Agent 返回分析、代码或操作建议。面板支持 SSE/WebSocket 流式输出，实时显示 Agent 的思考过程和生成内容。Agent 生成的代码块附带"插入到编辑器"按钮，一键将代码插入到当前编辑位置。

## 验收标准

- [ ] AC-1: 面板占据 Web-IDE 右侧，与左侧编辑器/Notebook 并排，支持拖拽调整分栏比例（最小 20%，最大 80%）
- [ ] AC-2: 消息输入框支持多行输入（Shift+Enter 换行，Enter 发送）
- [ ] AC-3: Agent 响应通过 SSE 流式显示，用户看到逐字输出效果
- [ ] AC-4: 代码块（```python ... ```）渲染为带语法高亮的代码卡片，附"插入到编辑器"和"复制"按钮
- [ ] AC-5: 快捷键 `Cmd+K` 聚焦到 Agent Chat 输入框
- [ ] AC-6: 对话历史在项目切换时保留，刷新页面后恢复（最近 50 条消息）
- [ ] AC-7: 发送消息时显示加载状态，Agent 响应完成后恢复输入
- [ ] AC-8: 支持停止生成按钮，中断当前 Agent 响应

## 接口定义

```typescript
// types/chat.ts
interface ChatMessage {
  id: string;
  role: "user" | "assistant" | "system";
  content: string;
  timestamp: string;
  metadata?: {
    toolCalls?: ToolCall[];
    thinkingSteps?: ThinkingStep[];  // 见 U-05
  };
}

interface ToolCall {
  toolName: string;
  input: Record<string, unknown>;
  output?: string;
  status: "pending" | "running" | "completed" | "failed";
}

// SSE 事件格式
interface StreamEvent {
  type: "text_delta" | "tool_use" | "tool_result" | "thinking" | "done" | "error";
  data: string | ToolCall | ThinkingStep;
}

// components/Chat/AgentChatPanel.tsx
interface AgentChatPanelProps {
  projectId: string;
  onInsertCode: (code: string) => void;  // 注入编辑器
}

// API
// POST /api/chat/stream
//   Body: { projectId, message, history: ChatMessage[] }
//   Response: text/event-stream (SSE)
//
// DELETE /api/chat/stream/{sessionId}  -> 中断生成
```

## 技术约束

- 流式传输使用 SSE（Server-Sent Events），通过 Next.js Route Handler 的 `ReadableStream` 实现
- 代码高亮使用 `react-syntax-highlighter` 或 `shiki`，与编辑器主题保持一致
- 对话历史存储在 Zustand store + localStorage（最近 50 条），不依赖后端持久化
- 分栏使用 `react-resizable-panels` 库
- Agent 后端通过 `/api/chat/stream` 代理，不直接从前端调用 Agent Core
- 消息 ID 使用 UUID v4，保证唯一性

## 测试策略

- 单元测试：消息列表渲染（user/assistant 消息样式区分）；代码块提取和渲染
- 集成测试：发送消息 -> 验证 SSE 流式响应 -> 验证消息追加到列表
- E2E（Playwright）：发送"写一个 Python 函数计算 IV 值" -> 验证响应包含代码块 -> 点击"插入到编辑器" -> 验证编辑器内容更新

## 依赖关系

- 被阻塞：[A-10]
- 阻塞：[U-05, U-06, U-07]

## 参考

- MVP_SPEC.md Section 3.4
