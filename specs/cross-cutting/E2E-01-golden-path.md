---
id: "E2E-01"
module: "cross-cutting"
title: "黄金路径端到端测试"
priority: P0
status: draft
owner: ""
dependencies: []
milestone: "W8"
---

# [E2E-01] 黄金路径端到端测试

## 概述

实现覆盖平台核心价值主张的端到端"黄金路径"测试，模拟真实用户从打开 Web-IDE 到完成欺诈检测模型训练的完整流程。黄金路径测试验证所有 P0 功能的集成正确性，是 MVP 发布的最终质量门禁。测试使用 Playwright 驱动浏览器，通过真实的 Docker Compose 环境执行。

## 验收标准

- [ ] AC-1: 黄金路径测试全程通过，耗时 <15 分钟
- [ ] AC-2: 测试覆盖以下完整流程（见下方流程定义）
- [ ] AC-3: 测试在 CI 环境（GitHub Actions）中可重复执行，不依赖外部状态
- [ ] AC-4: 测试失败时生成截图和视频录制，作为 CI Artifact 保存
- [ ] AC-5: 测试前自动执行数据初始化（加载欺诈检测数据集 + RAG 文档）
- [ ] AC-6: 测试后自动清理（重置数据库状态），不影响下次执行

## 接口定义

```typescript
// tests/e2e/golden-path.spec.ts

import { test, expect } from "@playwright/test";

/**
 * 黄金路径：欺诈检测模型训练
 *
 * 步骤 1: 项目创建
 *   - 打开 Web-IDE (http://localhost:3001)
 *   - 创建新项目 "fraud-detection-demo"
 *   - 验证文件浏览器显示项目目录
 *
 * 步骤 2: Agent 对话 - 数据探索
 *   - 在 Agent Chat 输入: "帮我探索欺诈检测数据集的基本统计信息"
 *   - 验证 Agent 调用 rag_search 工具（思考链显示）
 *   - 验证 Agent 生成 Python 代码（数据加载 + describe()）
 *   - 点击"插入到 Notebook"
 *   - 验证 Notebook 出现新 Cell
 *
 * 步骤 3: Notebook 执行
 *   - 执行数据探索 Cell (Cmd+Enter)
 *   - 验证输出显示数据集统计（284807 行，30 列）
 *
 * 步骤 4: 特征工程
 *   - 在 Agent Chat 输入: "为 V1-V10 和 Amount 创建 Feast 特征视图"
 *   - 验证 HITL 弹窗出现（feature_store_write 操作）
 *   - 点击"确认执行"
 *   - 验证特征视图注册成功（侧边栏显示新特征视图）
 *
 * 步骤 5: 特征物化
 *   - 在 Agent Chat 输入: "物化刚创建的特征视图"
 *   - 验证 HITL 弹窗出现
 *   - 确认执行
 *   - 验证物化任务完成（状态轮询）
 *
 * 步骤 6: 模型训练
 *   - 在 Agent Chat 输入: "使用 LightGBM 训练欺诈检测模型，目标 AUC > 0.95"
 *   - 验证 Agent 生成训练代码
 *   - 插入到 Notebook 并执行
 *   - 验证输出包含 AUC 指标
 *
 * 步骤 7: 实验查看
 *   - 打开实验对比看板
 *   - 验证 MLflow 中出现新实验记录
 *   - 验证 AUC > 0.95
 */

test("golden path: fraud detection model training", async ({ page }) => {
  // Step 1: Project creation
  await page.goto("http://localhost:3001");
  await page.click('[data-testid="new-project-btn"]');
  await page.fill('[data-testid="project-name-input"]', "fraud-detection-demo");
  await page.click('[data-testid="create-project-submit"]');
  await expect(page.locator('[data-testid="file-explorer"]')).toBeVisible();

  // Step 2: Agent conversation - data exploration
  await page.fill('[data-testid="chat-input"]',
    "帮我探索欺诈检测数据集的基本统计信息");
  await page.keyboard.press("Enter");
  await expect(page.locator('[data-testid="thinking-chain"]')).toBeVisible({ timeout: 10000 });
  await expect(page.locator('[data-testid="tool-call-rag_search"]')).toBeVisible();
  await expect(page.locator('[data-testid="code-block"]')).toBeVisible({ timeout: 30000 });
  await page.click('[data-testid="insert-to-notebook"]');

  // Step 3: Execute notebook cell
  await page.keyboard.press("Meta+Enter");
  await expect(page.locator('[data-testid="cell-output"]')).toContainText("284807", { timeout: 30000 });

  // Steps 4-7: ... (feature engineering, materialization, training, experiment view)
});
```

```yaml
# playwright.config.ts 关键配置
# timeout: 900000  (15 分钟)
# retries: 1       (失败重试 1 次)
# reporter: [["html"], ["junit", { outputFile: "test-results/junit.xml" }]]
# use:
#   baseURL: "http://localhost:3001"
#   video: "retain-on-failure"
#   screenshot: "only-on-failure"
#   trace: "retain-on-failure"
```

## 技术约束

- 测试框架：Playwright ≥1.44，使用 TypeScript
- 测试环境：完整 Docker Compose 栈（NFR-02），CI 中通过 `docker compose up -d` 启动
- 数据初始化：测试前执行 `make seed`（加载欺诈检测数据集 + 180 份 RAG 文档）
- 等待策略：使用 Playwright 的 `waitForSelector` 和 `waitForResponse`，不使用固定 `sleep`
- 测试隔离：每次测试前创建新项目，测试后通过 API 删除，不依赖数据库清理
- CI 资源：GitHub Actions `ubuntu-latest`，4 核 16GB，测试超时 20 分钟

## 测试策略

- 黄金路径：完整 7 步流程，验证核心价值主张
- 关键路径变体：仅验证 Agent Chat + 代码插入（不含特征工程），用于快速冒烟测试
- 失败恢复：HITL 弹窗取消后，验证 Agent 给出替代方案（不崩溃）

## 依赖关系

- 被阻塞：[所有 P0 功能]
- 阻塞：[]

## 参考

- MVP_SPEC.md Section 6（验收测试）
- Playwright: https://playwright.dev/docs/intro
