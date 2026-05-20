---
id: "NFR-03"
module: "cross-cutting"
title: "测试覆盖率 ≥70%"
priority: P0
status: draft
owner: ""
dependencies: []
milestone: "W8"
---

# [NFR-03] 测试覆盖率 ≥70%

## 概述

建立全平台统一的测试覆盖率标准，要求所有模块的代码覆盖率 ≥70%。包括 Python 后端（pytest + coverage）和 TypeScript 前端（Jest/Vitest）的覆盖率配置、CI 门禁和覆盖率报告。覆盖率不达标时 CI 流水线失败，阻止合并。

## 验收标准

- [ ] AC-1: Python 后端各模块（agent-core、mcp-gateway、rag-engine、feature-store-adapter）覆盖率 ≥70%
- [ ] AC-2: TypeScript 前端（apps/web）覆盖率 ≥70%（行覆盖率）
- [ ] AC-3: CI 流水线（GitHub Actions）在覆盖率 <70% 时失败，阻止 PR 合并
- [ ] AC-4: 覆盖率报告上传到 Codecov 或作为 CI Artifact 保存
- [ ] AC-5: 提供 `make test` 命令运行全部测试并生成覆盖率报告
- [ ] AC-6: 测试运行时间 <5 分钟（单元测试 + 集成测试，不含 E2E）
- [ ] AC-7: 排除以下文件的覆盖率统计：迁移文件、配置文件、`__init__.py`、类型定义文件

## 接口定义

```toml
# pyproject.toml (每个 Python 包)
[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"
addopts = "--cov=src --cov-report=term-missing --cov-report=xml --cov-fail-under=70"

[tool.coverage.run]
source = ["src"]
omit = [
    "*/migrations/*",
    "*/config.py",
    "*/__init__.py",
    "*/conftest.py",
]

[tool.coverage.report]
fail_under = 70
show_missing = true
```

```json
// vitest.config.ts (apps/web)
{
  "test": {
    "coverage": {
      "provider": "v8",
      "reporter": ["text", "lcov", "html"],
      "thresholds": {
        "lines": 70,
        "functions": 70,
        "branches": 60,
        "statements": 70
      },
      "exclude": [
        "**/*.d.ts",
        "**/types/**",
        "**/*.config.*",
        "**/node_modules/**"
      ]
    }
  }
}
```

```yaml
# .github/workflows/test.yml (关键步骤)
# - name: Run Python tests
#   run: |
#     cd packages/agent-core && pytest --cov-fail-under=70
#     cd packages/mcp-gateway && pytest --cov-fail-under=70
#     cd packages/rag-engine && pytest --cov-fail-under=70
#     cd packages/feature-store-adapter && pytest --cov-fail-under=70
#
# - name: Run Frontend tests
#   run: |
#     cd apps/web && pnpm test --coverage
```

## 技术约束

- Python 测试框架：`pytest` ≥8.0 + `pytest-asyncio` + `pytest-cov`
- Python mock 库：`unittest.mock` + `pytest-mock`
- TypeScript 测试框架：`vitest` ≥1.6（与 Next.js 14 兼容）+ `@testing-library/react`
- 覆盖率工具：Python 使用 `coverage.py`，TypeScript 使用 `v8`
- CI 环境：GitHub Actions，使用 `ubuntu-latest`
- 测试数据库：使用 `testcontainers-python` 启动临时 PostgreSQL/Redis，不 mock 数据库
- 集成测试与单元测试分离：`tests/unit/` 和 `tests/integration/`，可分别运行

## 测试策略

- 单元测试：覆盖所有业务逻辑函数，mock 外部依赖（数据库、HTTP 请求）
- 集成测试：使用 testcontainers 启动真实数据库，测试完整数据流
- 覆盖率豁免：通过 `# pragma: no cover` 注释排除无法测试的代码（如 `if __name__ == "__main__"`）

## 依赖关系

- 被阻塞：[]
- 阻塞：[]

## 参考

- MVP_SPEC.md Section 4（质量要求）
- pytest-cov: https://pytest-cov.readthedocs.io/
- Vitest Coverage: https://vitest.dev/guide/coverage
