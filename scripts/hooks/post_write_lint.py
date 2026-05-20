#!/usr/bin/env python3
"""Post-write hook: lint and syntax-check Python files."""
from __future__ import annotations

import json
import subprocess
import sys


def main() -> None:
    file_path = sys.argv[1] if len(sys.argv) > 1 else ""

    if not file_path.endswith(".py"):
        return

    issues: list[str] = []

    # Syntax check via ast.parse
    try:
        with open(file_path) as f:
            source = f.read()
        compile(source, file_path, "exec")
    except SyntaxError as e:
        issues.append(f"SyntaxError line {e.lineno}: {e.msg}")

    # Ruff check (if available)
    try:
        result = subprocess.run(
            ["ruff", "check", "--select=E,F,I,W,UP,B,SIM", "--no-fix", file_path],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.stdout.strip():
            for line in result.stdout.strip().split("\n")[:5]:
                issues.append(line)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass  # ruff not installed or timed out, skip

    if issues:
        output = {"status": "warn", "file": file_path, "issues": issues}
        print(json.dumps(output, ensure_ascii=False))


if __name__ == "__main__":
    main()
