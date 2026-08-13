#!/usr/bin/env python3
"""Run the Agent Base frontend release-hardening baseline."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


COMMANDS = [
    ["pnpm", "lint"],
    ["pnpm", "typecheck"],
    ["pnpm", "test"],
    ["pnpm", "build"],
]


def main() -> int:
    project_root = Path(__file__).resolve().parents[1]
    frontend_dir = project_root / "frontend"
    env = os.environ.copy()
    env.setdefault("SKIP_ENV_VALIDATION", "1")
    env.setdefault("AGENT_BASE_AUTH_DISABLED", "1")

    for command in COMMANDS:
        print("Running frontend check:")
        print("  cd frontend && " + " ".join(command))
        status = subprocess.call(command, cwd=frontend_dir, env=env)
        if status != 0:
            return status
    return 0


if __name__ == "__main__":
    sys.exit(main())
