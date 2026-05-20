---
id: "U-10"
module: "web-ide"
title: "暗色/亮色主题切换"
priority: P2
status: draft
owner: ""
dependencies: []
milestone: "W8"
---

# [U-10] 暗色/亮色主题切换

## 概述

提供全局暗色/亮色主题切换功能，主题变更同步应用到所有 UI 组件（shadcn/ui）和 Monaco 编辑器。用户偏好持久化存储，刷新页面后保持选择。默认跟随系统主题（`prefers-color-scheme`）。

## 验收标准

- [ ] AC-1: 顶部导航栏提供主题切换按钮（太阳/月亮图标），点击切换暗色/亮色
- [ ] AC-2: 主题切换立即生效，无页面刷新，所有组件同步更新
- [ ] AC-3: Monaco 编辑器主题同步切换（暗色: `vs-dark`，亮色: `vs`）
- [ ] AC-4: 用户选择持久化到 localStorage，刷新页面后恢复
- [ ] AC-5: 首次访问时跟随系统主题（`window.matchMedia('(prefers-color-scheme: dark)')`）
- [ ] AC-6: 支持第三种选项"跟随系统"，系统主题变更时自动切换

## 接口定义

```typescript
// types/theme.ts
type Theme = "light" | "dark" | "system";

// hooks/useTheme.ts
interface UseThemeReturn {
  theme: Theme;
  resolvedTheme: "light" | "dark";  // system 解析后的实际主题
  setTheme: (theme: Theme) => void;
}

// components/ThemeToggle.tsx
// 使用 next-themes 库实现，与 shadcn/ui 集成

// Monaco 主题同步
// useEffect(() => {
//   monaco.editor.setTheme(resolvedTheme === "dark" ? "vs-dark" : "vs");
// }, [resolvedTheme]);
```

## 技术约束

- 使用 `next-themes` 库（与 Next.js 14 和 shadcn/ui 官方推荐集成方式一致）
- CSS 变量方案：shadcn/ui 的主题通过 CSS 变量实现，切换时修改 `<html>` 的 `class`（`dark`/`light`）
- 避免 FOUC（Flash of Unstyled Content）：在 `<head>` 中内联脚本读取 localStorage 并设置初始主题
- Monaco 编辑器主题通过 `monaco.editor.setTheme()` 同步，不重新挂载编辑器

## 测试策略

- 单元测试：useTheme hook 的 setTheme 逻辑；localStorage 读写
- 集成测试：切换到暗色主题，验证 `<html>` class 包含 `dark`；刷新页面，验证主题持久化
- 视觉回归测试：截图对比暗色/亮色主题下的关键页面

## 依赖关系

- 被阻塞：[]
- 阻塞：[]

## 参考

- MVP_SPEC.md Section 3.4
- next-themes: https://github.com/pacocoursey/next-themes
