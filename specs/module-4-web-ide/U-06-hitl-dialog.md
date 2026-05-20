---
id: "U-06"
module: "web-ide"
title: "HITL 确认弹窗"
priority: P0
status: draft
owner: ""
dependencies: ["U-04"]
milestone: "W6"
---

# [U-06] HITL 确认弹窗

## 概述

Human-in-the-Loop（HITL）确认弹窗在 Agent 执行高风险操作前弹出，要求用户明确确认或拒绝。高风险操作包括：写入文件、执行代码、调用外部 API、修改特征视图等。弹窗展示操作详情和预期影响，用户确认后 Agent 继续执行，拒绝后 Agent 收到取消信号并调整策略。

## 验收标准

- [ ] AC-1: 以下操作触发 HITL 弹窗：写文件、执行 Shell 命令、调用 Feature Store 写入接口、部署模型
- [ ] AC-2: 弹窗显示：操作类型、操作描述、预期影响（如"将写入文件 /path/to/file.py"）
- [ ] AC-3: 弹窗提供"确认执行"（绿色）和"取消"（红色）两个按钮
- [ ] AC-4: 用户确认后，Agent 继续执行并在思考链（U-05）中记录"用户已确认"
- [ ] AC-5: 用户取消后，Agent 收到 `{"approved": false, "reason": "user_cancelled"}` 并停止该操作
- [ ] AC-6: 弹窗出现时，Agent Chat 输入框禁用，防止用户在等待确认时发送新消息
- [ ] AC-7: 弹窗超时（默认 60s）后自动取消，Agent 收到超时信号
- [ ] AC-8: 支持"记住此选择"复选框，对同类操作在当前会话内不再弹窗

## 接口定义

```typescript
// types/hitl.ts
interface HitlRequest {
  requestId: string;
  operationType: "write_file" | "execute_code" | "api_call" | "feature_store_write" | "deploy_model";
  title: string;
  description: string;
  details: {
    // write_file
    filePath?: string;
    content?: string;
    // execute_code
    code?: string;
    // api_call
    endpoint?: string;
    method?: string;
    body?: unknown;
    // feature_store_write
    featureViewName?: string;
    // deploy_model
    modelName?: string;
    environment?: string;
  };
  riskLevel: "low" | "medium" | "high";
  timeoutSeconds: number;
}

interface HitlResponse {
  requestId: string;
  approved: boolean;
  reason?: "user_approved" | "user_cancelled" | "timeout" | "remembered";
  rememberForSession?: boolean;
}

// SSE 事件（触发弹窗）
// type: "hitl_request"
// data: HitlRequest

// API（用户响应）
// POST /api/hitl/respond
//   Body: HitlResponse
//   Response: 204

// components/HITL/HitlDialog.tsx
interface HitlDialogProps {
  request: HitlRequest | null;
  onRespond: (response: HitlResponse) => void;
}
```

## 技术约束

- 弹窗使用 shadcn/ui 的 `Dialog` 组件，覆盖整个视口（`z-index: 9999`）
- HITL 请求通过 SSE 流接收（与 Agent 响应同一连接），不使用独立 WebSocket
- 用户响应通过 `POST /api/hitl/respond` 发送，后端将结果传递给 Agent Core
- "记住此选择"存储在 sessionStorage，页面刷新后重置
- 弹窗倒计时使用 `useInterval` hook，每秒更新剩余时间显示
- 高风险操作（`riskLevel: "high"`）不支持"记住此选择"

## 测试策略

- 单元测试：HitlDialog 渲染（不同 operationType 的显示内容）；超时倒计时逻辑
- 集成测试：模拟 Agent 发送 `hitl_request` SSE 事件，验证弹窗弹出；点击确认，验证 `/api/hitl/respond` 被调用
- E2E（Playwright）：触发文件写入操作 -> 验证弹窗出现 -> 点击取消 -> 验证文件未被写入

## 依赖关系

- 被阻塞：[U-04]
- 阻塞：[]

## 参考

- MVP_SPEC.md Section 3.4
