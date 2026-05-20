#!/usr/bin/env python3
"""Pre-bash hook: block dangerous shell commands.

BLOCKING: exits non-zero if command matches destructive patterns.
"""
from __future__ import annotations

import json
import os
import re
import sys

DANGEROUS_PATTERNS = [
    (r"rm\s+-rf\s+/(?!\S)", "rm -rf / (recursive delete from root)"),
    (r"rm\s+-rf\s+\*", "rm -rf * (recursive delete all)"),
    (r"DROP\s+DATABASE", "DROP DATABASE"),
    (r"DROP\s+TABLE", "DROP TABLE"),
    (r"TRUNCATE\s+TABLE", "TRUNCATE TABLE"),
    (r"git\s+push\s+.*--force\s+.*main", "force push to main"),
    (r"git\s+push\s+.*--force\s+.*master", "force push to master"),
    (r"mkfs\.", "filesystem format command"),
    (r"dd\s+if=.*of=/dev/", "dd write to device"),
]


def main() -> None:
    # The command is passed via environment variable or stdin
    command = os.environ.get("CLAUDE_BASH_COMMAND", "")
    if not command:
        # Try reading from stdin
        try:
            command = sys.stdin.read()
        except Exception:
            return

    for pattern, description in DANGEROUS_PATTERNS:
        if re.search(pattern, command, re.IGNORECASE):
            output = {
                "status": "block",
                "reason": f"Dangerous command detected: {description}",
                "command": command[:200],
            }
            print(json.dumps(output, ensure_ascii=False))
            sys.exit(1)


if __name__ == "__main__":
    main()
