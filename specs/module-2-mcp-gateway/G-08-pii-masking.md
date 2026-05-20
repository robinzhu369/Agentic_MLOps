---
id: "G-08"
module: "mcp-gateway"
title: "PII 脱敏"
priority: P0
status: draft
owner: ""
dependencies: ["G-04"]
milestone: "W2"
---

# [G-08] PII 脱敏

## 概述

自动检测并脱敏工具调用请求参数和响应内容中的个人身份信息（PII），包括身份证号码和银行卡号。脱敏在 MCP Gateway 层统一执行，确保 PII 不出现在审计日志、Agent 上下文或下游系统中。脱敏操作对调用方透明，不改变响应结构。

## 验收标准

- [ ] AC-1: 工具调用参数中的 18 位身份证号码自动替换为 `[ID_MASKED]`，脱敏在转发到 MCP Server 前执行
- [ ] AC-2: 工具响应内容中的 16 位银行卡号（Luhn 校验通过）自动替换为 `[CARD_MASKED]`，脱敏在返回给调用方前执行
- [ ] AC-3: 脱敏操作不改变 JSON 结构，只替换字符串值中的 PII 内容，保留字段名和数据类型
- [ ] AC-4: 脱敏规则可扩展，通过配置文件添加新的 PII 模式（正则表达式 + 替换标签），无需修改代码
- [ ] AC-5: 脱敏操作 P99 延迟 ≤ 5ms（针对 10KB 以内的 JSON 内容）

## 接口定义

```python
from pydantic import BaseModel
from typing import Any
import re


class PIIPattern(BaseModel):
    name: str                            # e.g. "chinese_id_card"
    pattern: str                         # Regex pattern string
    replacement: str                     # e.g. "[ID_MASKED]"
    description: str


# Built-in patterns:
BUILTIN_PATTERNS = [
    PIIPattern(
        name="chinese_id_card",
        pattern=r"\b[1-9]\d{5}(?:18|19|20)\d{2}(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01])\d{3}[\dXx]\b",
        replacement="[ID_MASKED]",
        description="18-digit Chinese national ID card number",
    ),
    PIIPattern(
        name="bank_card",
        pattern=r"\b(?:\d[ -]?){15,16}\b",  # Combined with Luhn check
        replacement="[CARD_MASKED]",
        description="16-digit bank card number (Luhn validated)",
    ),
]


class PIIMasker:
    def __init__(self, extra_patterns: list[PIIPattern] | None = None):
        """
        Initialize with built-in patterns plus any extra patterns from config.
        """
        ...

    def mask_dict(self, data: dict[str, Any]) -> tuple[dict[str, Any], int]:
        """
        Recursively mask PII in all string values of a dict.

        Args:
            data: Input dict (tool arguments or response content).

        Returns:
            (masked_dict, count_of_replacements)
        """
        ...

    def mask_string(self, text: str) -> tuple[str, int]:
        """
        Apply all PII patterns to a string.

        Returns:
            (masked_text, count_of_replacements)
        """
        ...

    def _luhn_check(self, number: str) -> bool:
        """Validate bank card number using Luhn algorithm."""
        ...

    @classmethod
    def from_config(cls, config_path: str) -> "PIIMasker":
        """Load extra PII patterns from YAML config file."""
        ...
```

## 技术约束

- 脱敏使用预编译正则表达式，启动时编译，运行时不重新编译
- 银行卡号检测需通过 Luhn 算法二次验证，避免误判普通数字序列
- 脱敏递归处理嵌套 JSON，最大递归深度 10 层，超出深度的内容不处理（记录警告）
- 额外 PII 模式配置文件路径：`config/pii_patterns.yaml`，支持热重载
- 脱敏操作不修改原始对象，返回新的 dict/string

## 测试策略

- 单元测试：验证 18 位身份证号码被正确脱敏；验证 Luhn 校验通过的银行卡号被脱敏，未通过的不被脱敏；测试嵌套 JSON 递归脱敏；测试脱敏不改变 JSON 结构；测试 P99 延迟 ≤ 5ms（10KB 内容）
- 集成测试：与 G-04 联调，验证请求参数和响应内容均经过脱敏；验证审计日志中不含原始 PII
- E2E：包含 PII 数据的工具调用，验证 Agent 收到的响应中 PII 已被替换

## 依赖关系

- 被阻塞：[G-04]
- 阻塞：[]

## 参考

- MVP_SPEC.md Section 3.2
