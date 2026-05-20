#!/usr/bin/env python3
"""Post-write hook: check for forbidden code patterns.

ADVISORY: outputs warnings but does not block (exit 0).
"""
from __future__ import annotations

import json
import re
import sys

# Patterns to check (regex, description, exclude_paths)
FORBIDDEN_PATTERNS = [
    (r"^\s*except\s*:", "bare except (catch specific exceptions)", []),
    (r"(?<!\w)print\s*\(", "print() for logging (use structlog)", ["tests/", "scripts/", "test_"]),
    (r"datetime\.now\(\s*\)", "datetime.now() without timezone (use datetime.now(tz=timezone.utc))", []),
    (r"^\s*from\s+\S+\s+import\s+\*", "wildcard import (use explicit imports)", []),
    (r"def\s+\w+\s*\([^)]*=\s*\[\]", "mutable default argument [] (use None + assignment in body)", []),
    (r"def\s+\w+\s*\([^)]*=\s*\{\}", "mutable default argument {} (use None + assignment in body)", []),
]


def should_skip(file_path: str, exclude_paths: list[str]) -> bool:
    return any(exc in file_path for exc in exclude_paths)


def main() -> None:
    file_path = sys.argv[1] if len(sys.argv) > 1 else ""

    if not file_path.endswith(".py"):
        return

    try:
        with open(file_path) as f:
            lines = f.readlines()
    except (FileNotFoundError, PermissionError):
        return

    warnings: list[str] = []
    for i, line in enumerate(lines, 1):
        for pattern, description, exclude_paths in FORBIDDEN_PATTERNS:
            if should_skip(file_path, exclude_paths):
                continue
            if re.search(pattern, line):
                warnings.append(f"line {i}: {description}")

    if warnings:
        output = {"status": "warn", "file": file_path, "warnings": warnings[:10]}
        print(json.dumps(output, ensure_ascii=False))


if __name__ == "__main__":
    main()
