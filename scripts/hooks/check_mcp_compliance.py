#!/usr/bin/env python3
"""Post-write hook: enforce MCP compliance in agent-core.

BLOCKING: exits non-zero if agent-core imports tool libraries directly.
"""
from __future__ import annotations

import json
import re
import sys

# Forbidden imports when file is inside packages/agent-core/ or packages/agent_core/
FORBIDDEN_IMPORTS = [
    (r"^\s*(import|from)\s+jupyter_client", "jupyter_client (use mcp-jupyter via MCP Gateway)"),
    (r"^\s*(import|from)\s+feast", "feast (use mcp-feature-store via MCP Gateway)"),
    (r"^\s*(import|from)\s+sqlalchemy", "sqlalchemy for direct DB (use mcp-data-catalog via MCP Gateway)"),
    (r"^\s*(import|from)\s+nbformat", "nbformat (use mcp-jupyter via MCP Gateway)"),
    (r"^\s*(import|from)\s+nbclient", "nbclient (use mcp-jupyter via MCP Gateway)"),
]

AGENT_CORE_PATTERNS = ["packages/agent-core/", "packages/agent_core/"]


def main() -> None:
    file_path = sys.argv[1] if len(sys.argv) > 1 else ""

    if not file_path.endswith(".py"):
        return

    # Only check files in agent-core
    is_agent_core = any(pattern in file_path for pattern in AGENT_CORE_PATTERNS)
    if not is_agent_core:
        return

    try:
        with open(file_path) as f:
            lines = f.readlines()
    except (FileNotFoundError, PermissionError):
        return

    violations: list[str] = []
    for i, line in enumerate(lines, 1):
        for pattern, description in FORBIDDEN_IMPORTS:
            if re.match(pattern, line):
                violations.append(f"line {i}: forbidden import of {description}")

    if violations:
        output = {
            "status": "block",
            "file": file_path,
            "reason": "agent-core must not import tool libraries directly. All tool access goes through MCP Gateway.",
            "violations": violations,
        }
        print(json.dumps(output, ensure_ascii=False))
        sys.exit(1)


if __name__ == "__main__":
    main()
