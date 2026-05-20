---
id: "U-05"
module: "web-ide"
title: "思考链可视化"
priority: P0
status: draft
owner: ""
dependencies: ["U-04", "A-10"]
milestone: "W6"
---

# [U-05] 思考链可视化

## 概述

在 Agent Chat 面板中可视化展示 Agent 的推理过程（Chain-of-Thought），包括工具调用、中间思考步骤和 Observation 输出。思考链以可折叠的时间线形式展示，默认折叠以节省空间，用户可展开查看完整推理过程。该功能提升 Agent 行为的可解释性，帮助用户理解 Agent 的决策依据。

## 验收标准

- [ ] AC-1: Agent 每次工具调用在思考链中显示：工具名称、输入参数、执行状态（运行中/完成/失败）
- [ ] AC-2: 思考链以可折叠面板展示，默认折叠，标题显示"思考过程（N 步）"
- [ ] AC-3: 工具调用的 Observation（输出）在折叠面板内显示，超过 500 字符时截断并提供"展开"链接
- [ ] AC-4: 思考步骤按时间顺序排列，每步显示相对时间戳（如"2s 前"）
- [ ] AC-5: 工具调用状态实时更新：调用中显示 spinner，完成后显示 ✓，失败显示 ✗
- [ ] AC-6: 支持 `Cmd+Shift+T` 快捷键切换思考链面板的展开/折叠状态
- [ ] AC-7: 思考链数据通过 SSE 流式接收，与 Agent 文本响应同步显示

## 接口定义

```typescript
// types/thinking.ts
interface ThinkingStep {
  id: string;
  stepType: "tool_call" | "observation" | "reasoning";
  timestamp: string;
  durationMs?: number;
  // tool_call 类型
  toolName?: string;
  toolInput?: Record<string, unknown>;
  toolStatus?: "running" | "completed" | "failed";
  // observation 类型
  observation?: string;
  truncated?: boolean;
  // reasoning 类型（Agent 内部思考文本，如有）
  reasoning?: string;
}

// SSE 事件（扩展 U-04 的 StreamEvent）
// type: "thinking_step"
// data: ThinkingStep

// components/Chat/ThinkingChain.tsx
interface ThinkingChainProps {
  steps: ThinkingStep[];
  isStreaming: boolean;
  defaultExpanded?: boolean;
}

// components/Chat/ThinkingStep.tsx
interface ThinkingStepProps {
  step: ThinkingStep;
  index: number;
}

// 工具调用展示格式
// ┌─ 🔧 rag_search                    [2s] ✓
// │  Input: { query: "KYC 要求", domain: "compliance" }
// │  Output: 找到 5 个相关文档片段...  [展开]
// └─────────────────────────────────────────
```

## 技术约束

- 思考链组件使用 `framer-motion` 实现折叠/展开动画
- Observation 文本截断阈值 500 字符，截断时显示"...展开查看完整输出"
- 思考链步骤存储在 ChatMessage 的 `metadata.thinkingSteps` 字段
- 工具调用 JSON 输入使用 `react-json-view` 或自定义 JSON 渲染器展示
- 思考链面板高度自适应内容，最大高度 400px，超出时内部滚动

## 测试策略

- 单元测试：ThinkingChain 组件渲染（空步骤、单步骤、多步骤）；折叠/展开状态切换
- 集成测试：模拟包含 3 个工具调用的 SSE 流，验证思考链步骤按顺序追加
- E2E（Playwright）：触发需要 RAG 检索的 Agent 请求，验证思考链显示 `rag_search` 工具调用及其结果

## 依赖关系

- 被阻塞：[U-04, A-10]
- 阻塞：[]

## 参考

- MVP_SPEC.md Section 3.4
