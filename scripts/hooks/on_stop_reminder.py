#!/usr/bin/env python3
"""Stop hook: session-end reminder checklist.

ADVISORY: outputs a reminder for the developer.
"""
from __future__ import annotations

import json


def main() -> None:
    reminder = {
        "status": "reminder",
        "checklist": [
            "更新 specs/_index.md 中相关 spec 的状态",
            "对修改的模块运行 pytest",
            "确认 commit message 遵循 Conventional Commits 格式",
            "检查是否有未完成的 TODO 需要记录",
        ],
    }
    print(json.dumps(reminder, ensure_ascii=False))


if __name__ == "__main__":
    main()
