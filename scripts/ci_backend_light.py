#!/usr/bin/env python3
"""Run the Agent Base lightweight backend release regression suite.

This script is the single source of truth for the quick backend gate used by
local developers and CI. Keep it focused on tests that do not require optional
provider credentials, Kubernetes, or a live LLM.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path


LIGHTWEIGHT_TESTS = [
    "tests/test_record_replay_gateway_env.py",
    "tests/test_sandbox_limits.py",
    "tests/test_mcp_stdio_allowlist_env.py",
    "tests/test_trace_environment.py",
    "tests/test_aio_sandbox_local_backend.py",
    "tests/test_sandbox_memory_profile_script.py",
    "tests/test_dev_entrypoint.py",
    "tests/test_gateway_runtime_cleanup.py",
    "tests/test_frontend_backend_contract.py",
    "tests/test_channel_service_env.py",
    "tests/test_agent_base_facade.py",
    "tests/test_internal_auth.py",
    "tests/test_docker_sandbox_mode_detection.py",
    "tests/test_detect_uv_extras.py",
]


def main() -> int:
    project_root = Path(__file__).resolve().parents[1]
    backend_dir = project_root / "backend"

    env = os.environ.copy()
    env.setdefault("PYTHONIOENCODING", "utf-8")
    env.setdefault("PYTHONUTF8", "1")
    env.setdefault("PYTHONPATH", ".")
    env.setdefault("UV_PROJECT_ENVIRONMENT", str(project_root / ".venv"))

    tests = list(LIGHTWEIGHT_TESTS)
    if os.name == "nt" and shutil.which("sh") is None:
        tests.remove("tests/test_dev_entrypoint.py")
        print("Skipping tests/test_dev_entrypoint.py because POSIX sh is not available on this Windows host.")

    command = ["uv", "run", "python", "-m", "pytest", *tests, "-q"]
    print("Running backend lightweight regression:")
    print("  cd backend && " + " ".join(command))
    return subprocess.call(command, cwd=backend_dir, env=env)


if __name__ == "__main__":
    sys.exit(main())
