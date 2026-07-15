#!/usr/bin/env python3
"""Validate the production Docker Compose surface.

By default this performs a configuration-only smoke test so it can run in CI
without model credentials or a long-lived service stack. Pass ``--start`` to
build and start the stack, wait for the Gateway health endpoint, then tear it
down.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import time
import urllib.request
from contextlib import contextmanager
from pathlib import Path


def _compose_command() -> list[str] | None:
    docker = shutil.which("docker")
    if docker:
        return [docker, "compose"]
    docker_compose = shutil.which("docker-compose")
    if docker_compose:
        return [docker_compose]
    return None


def _run(command: list[str], *, cwd: Path, env: dict[str, str]) -> int:
    print("  " + " ".join(command))
    return subprocess.call(command, cwd=cwd, env=env)


def _smoke_env(project_root: Path) -> dict[str, str]:
    env = os.environ.copy()
    smoke_home = project_root / ".agent-base" / "ci-smoke"
    env.setdefault("AGENT_BASE_HOME", str(smoke_home))
    env.setdefault("AGENT_BASE_CONFIG_PATH", str(project_root / "configs" / "base.example.yaml"))
    env.setdefault("AGENT_BASE_EXTENSIONS_CONFIG_PATH", str(project_root / "extensions_config.example.json"))
    env.setdefault("AGENT_BASE_DOCKER_SOCKET", "/var/run/docker.sock")
    env.setdefault("AGENT_BASE_REPO_ROOT", str(project_root))
    env.setdefault("BETTER_AUTH_SECRET", "ci-smoke-not-for-production")
    env.setdefault("AGENT_BASE_INTERNAL_AUTH_TOKEN", "ci-smoke-internal-token")
    env.setdefault("PORT", "2026")
    return env


def _wait_for_health(url: str, timeout_seconds: float) -> bool:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=5) as response:
                if 200 <= response.status < 300:
                    return True
        except Exception:
            time.sleep(2)
    return False


@contextmanager
def _temporary_env_files(project_root: Path):
    """Create empty env files only when CI checkout does not provide them."""
    created: list[Path] = []
    candidates = [project_root / ".env", project_root / "frontend" / ".env"]
    try:
        for path in candidates:
            if path.exists():
                continue
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("# Created temporarily by scripts/docker_smoke.py\n", encoding="utf-8")
            created.append(path)
        yield
    finally:
        for path in created:
            try:
                path.unlink()
            except FileNotFoundError:
                pass


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--start",
        action="store_true",
        help="Build and start the compose stack, then verify /health and tear down.",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=120.0,
        help="Seconds to wait for /health when --start is used.",
    )
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parents[1]
    compose_file = project_root / "docker" / "docker-compose.yaml"
    compose = _compose_command()
    if compose is None:
        print("Docker Compose is not available; install Docker to run the smoke test.")
        return 1

    env = _smoke_env(project_root)

    with _temporary_env_files(project_root):
        print("Validating Docker Compose configuration:")
        config_status = _run([*compose, "-f", str(compose_file), "config"], cwd=project_root, env=env)
        if config_status != 0:
            return config_status

        if not args.start:
            print("Docker Compose configuration smoke test passed.")
            return 0

        project_name = "agent-base-ci-smoke"
        up_command = [
            *compose,
            "-p",
            project_name,
            "-f",
            str(compose_file),
            "up",
            "--build",
            "-d",
            "nginx",
            "frontend",
            "gateway",
        ]
        down_command = [*compose, "-p", project_name, "-f", str(compose_file), "down", "--remove-orphans"]

        try:
            up_status = _run(up_command, cwd=project_root, env=env)
            if up_status != 0:
                return up_status
            health_url = f"http://127.0.0.1:{env['PORT']}/health"
            if not _wait_for_health(health_url, args.timeout):
                print(f"Gateway health check timed out: {health_url}")
                return 1
            print("Docker Compose start smoke test passed.")
            return 0
        finally:
            _run(down_command, cwd=project_root, env=env)


if __name__ == "__main__":
    sys.exit(main())
