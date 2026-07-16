"""Start the local web agent stack with venv backend and Next.js frontend.

Defaults:
- Backend Gateway: http://127.0.0.1:10086
- Frontend Web:    http://127.0.0.1:9527

Run from the project root:
    python start_web_agent.py
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parent
BACKEND_DIR = ROOT / "backend"
FRONTEND_DIR = ROOT / "frontend"
ROOT_VENV_DIR = ROOT / ".venv"
FRONTEND_NODE_MODULES_DIR = FRONTEND_DIR / "node_modules"
DEFAULT_USER_ROOT = Path(r"C:\Users\Administrator\GP Agent")
DEFAULT_RUNTIME_HOME = DEFAULT_USER_ROOT / ".agent-base"
DEFAULT_WORKSPACE_ROOT = DEFAULT_USER_ROOT / "workspace"
DEFAULT_LOG_ROOT = ROOT / ".tools" / "logs"
DEFAULT_NODE = Path(
    r"C:\Users\Administrator\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe"
)


def configure_console_encoding() -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Start backend and frontend for the Government Project Declaration Agent.")
    parser.add_argument("--host", default="127.0.0.1", help="Host used by both services.")
    parser.add_argument("--backend-port", type=int, default=10086, help="Backend Gateway port.")
    parser.add_argument("--frontend-port", type=int, default=9527, help="Frontend Web port.")
    parser.add_argument("--backend-timeout", type=float, default=30.0, help="Seconds to wait for backend startup.")
    parser.add_argument("--frontend-timeout", type=float, default=45.0, help="Seconds to wait for frontend startup.")
    parser.add_argument("--warmup-timeout", type=float, default=45.0, help="Seconds to wait for each frontend warmup request.")
    parser.add_argument("--skip-warmup", action="store_true", help="Skip frontend route warmup after startup.")
    parser.add_argument(
        "--network-proxy",
        default=os.environ.get("HTTP_PROXY") or os.environ.get("HTTPS_PROXY") or "",
        help="Optional outbound network proxy, for example http://127.0.0.1:7897.",
    )
    parser.add_argument(
        "--node",
        default=str(DEFAULT_NODE) if DEFAULT_NODE.exists() else "node",
        help="Node.js executable path. Defaults to bundled Codex Node if available.",
    )
    parser.add_argument(
        "--log-dir",
        default=str(DEFAULT_LOG_ROOT),
        help="Directory for backend/frontend startup logs. Defaults to the project .tools/logs directory.",
    )
    reload_group = parser.add_mutually_exclusive_group()
    reload_group.add_argument("--reload", dest="reload", action="store_true", help="Enable backend uvicorn reload.")
    reload_group.add_argument("--no-reload", dest="reload", action="store_false", help="Disable backend uvicorn reload.")
    parser.set_defaults(reload=os.name != "nt")
    return parser.parse_args()


def load_dotenv(env: dict[str, str]) -> None:
    env_path = ROOT / ".env"
    if not env_path.exists():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in env:
            env[key] = value


def ensure_file(path: Path, message: str) -> None:
    if not path.exists():
        raise SystemExit(f"{message}: {path}")


def ensure_external_runtime_path(path: Path, message: str) -> Path:
    resolved = path.resolve()
    try:
        resolved.relative_to(ROOT.resolve())
    except ValueError:
        return resolved
    raise SystemExit(
        f"{message}: {resolved}. Runtime data paths must stay outside the source-code directory {ROOT}."
    )


def ensure_runtime_path(path: Path, message: str, *, allow_inside_source: bool = False) -> Path:
    resolved = path.resolve()
    if allow_inside_source:
        return resolved
    return ensure_external_runtime_path(path, message)


def is_port_open(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.5)
        return sock.connect_ex((host, port)) == 0


def tail_file(path: Path, max_lines: int = 40) -> str:
    if not path.exists():
        return ""
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    return "\n".join(lines[-max_lines:])


def print_process_logs(name: str, process: subprocess.Popen[str], max_lines: int = 40) -> None:
    stdout_path = getattr(process, "_agent_base_stdout_path", None)
    stderr_path = getattr(process, "_agent_base_stderr_path", None)
    if stdout_path:
        stdout_tail = tail_file(Path(stdout_path), max_lines=max_lines)
        if stdout_tail:
            print(f"[log] {name} stdout tail:", flush=True)
            print(stdout_tail, flush=True)
    if stderr_path:
        stderr_tail = tail_file(Path(stderr_path), max_lines=max_lines)
        if stderr_tail:
            print(f"[log] {name} stderr tail:", flush=True)
            print(stderr_tail, flush=True)


def ensure_processes_stable(processes: list[subprocess.Popen[str]], settle_seconds: float = 3.0) -> bool:
    deadline = time.time() + settle_seconds
    while time.time() < deadline:
        for process in processes:
            code = process.poll()
            if code is not None:
                name = getattr(process, "_agent_base_name", "process")
                print(f"[error] {name} exited during startup settle (exit code {code}).", flush=True)
                print_process_logs(name, process)
                return False
        time.sleep(0.5)
    return True


def wait_for_port(name: str, process: subprocess.Popen[str], host: str, port: int, timeout: float, settle_seconds: float = 1.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if is_port_open(host, port):
            time.sleep(settle_seconds)
            code = process.poll()
            if code is not None:
                print(f"[error] {name} exited after opening port {port} (exit code {code}).", flush=True)
                print_process_logs(name, process)
                return False
            print(f"[ok] {name} is listening at http://{host}:{port}", flush=True)
            return True
        code = process.poll()
        if code is not None:
            print(f"[error] {name} exited before opening port {port} (exit code {code}).", flush=True)
            print_process_logs(name, process)
            return False
        time.sleep(0.5)
    print(f"[error] {name} did not open port {port} within {timeout:.0f}s.", flush=True)
    print_process_logs(name, process)
    return False


def request_json(url: str, *, method: str = "GET", body: dict | None = None, timeout: float = 10.0) -> object:
    data = None
    headers: dict[str, str] = {}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        payload = response.read()
    if not payload:
        return None
    return json.loads(payload.decode("utf-8"))


def request_page(url: str, *, timeout: float) -> None:
    request = urllib.request.Request(url, headers={"User-Agent": "gp-agent-startup-warmup/1.0"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        response.read(1024)
        print(f"[warmup] {url} -> HTTP {response.status}", flush=True)


def first_project_and_thread(host: str, backend_port: int, timeout: float) -> tuple[str | None, str | None]:
    backend_base = f"http://{host}:{backend_port}"
    projects_payload = request_json(f"{backend_base}/api/projects", timeout=timeout)
    projects = projects_payload if isinstance(projects_payload, list) else []
    project_id = None
    for project in projects:
        if isinstance(project, dict) and isinstance(project.get("project_id"), str) and project["project_id"].strip():
            project_id = project["project_id"]
            break
    if not project_id:
        return None, None

    thread_payload = request_json(
        f"{backend_base}/api/threads/search",
        method="POST",
        body={"limit": 1, "offset": 0, "metadata": {"project_id": project_id}},
        timeout=timeout,
    )
    threads = thread_payload if isinstance(thread_payload, list) else []
    thread_id = None
    for thread in threads:
        if isinstance(thread, dict) and isinstance(thread.get("thread_id"), str) and thread["thread_id"].strip():
            thread_id = thread["thread_id"]
            break
    return project_id, thread_id


def warm_frontend_routes(args: argparse.Namespace) -> None:
    frontend_base = f"http://{args.host}:{args.frontend_port}"
    urls = [f"{frontend_base}/workspace/projects"]
    try:
        project_id, thread_id = first_project_and_thread(args.host, args.backend_port, timeout=min(args.warmup_timeout, 10.0))
    except (OSError, urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        print(f"[warmup] Could not discover project/thread for dynamic route warmup: {exc}", flush=True)
        project_id, thread_id = None, None

    if project_id:
        encoded_project = urllib.parse.quote(project_id, safe="")
        urls.append(f"{frontend_base}/workspace/projects/{encoded_project}")
        if thread_id:
            encoded_thread = urllib.parse.quote(thread_id, safe="")
            urls.append(f"{frontend_base}/workspace/projects/{encoded_project}/threads/{encoded_thread}")

    print(f"[warmup] Warming frontend routes ({len(urls)} request(s))...", flush=True)
    for url in urls:
        try:
            request_page(url, timeout=args.warmup_timeout)
        except (OSError, urllib.error.URLError, TimeoutError) as exc:
            print(f"[warmup] Failed to warm {url}: {exc}", flush=True)


def stop_existing_next_dev(frontend_dir: Path, frontend_port: int) -> None:
    """Stop stale Next dev servers for this frontend directory and port on Windows."""
    if os.name != "nt":
        return

    try:
        completed = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                (
                    "Get-CimInstance Win32_Process | "
                    "Where-Object { $_.Name -like 'node*' -and "
                    "$_.CommandLine -like '*next*dev*' -and "
                    "$_.CommandLine -like '*Government Project Declaration Agent*frontend*' -and "
                    f"$_.CommandLine -like '*--port*{frontend_port}*' }} | "
                    "Select-Object -ExpandProperty ProcessId"
                ),
            ],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except Exception as exc:
        print(f"[warn] Failed to inspect existing Next dev servers: {exc}", flush=True)
        return

    current_pid = os.getpid()
    pids = []
    for line in completed.stdout.splitlines():
        line = line.strip()
        if not line.isdigit():
            continue
        pid = int(line)
        if pid != current_pid:
            pids.append(pid)

    for pid in sorted(set(pids)):
        print(f"[stop] Existing Next dev server detected for {frontend_dir} on port {frontend_port}; stopping PID {pid}.", flush=True)
        subprocess.run(
            ["taskkill", "/PID", str(pid), "/F"],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )


def build_env(args: argparse.Namespace) -> dict[str, str]:
    env = os.environ.copy()
    load_dotenv(env)

    env.setdefault("PYTHONUTF8", "1")
    env.setdefault("PYTHONIOENCODING", "utf-8")
    env.setdefault("AGENT_BASE_PROJECT_ROOT", str(ROOT))
    env.setdefault("AGENT_BASE_HOME", str(DEFAULT_RUNTIME_HOME))
    env.setdefault("DEER_FLOW_HOME", env["AGENT_BASE_HOME"])
    env.setdefault("AGENT_BASE_HOST_BASE_DIR", env["AGENT_BASE_HOME"])
    env.setdefault("GOVERNMENT_PROJECT_WORKSPACE_ROOT", str(DEFAULT_WORKSPACE_ROOT))
    env.setdefault("AGENT_BASE_KNOWLEDGE_ROOT", str(Path(env["GOVERNMENT_PROJECT_WORKSPACE_ROOT"]) / "knowledge_base"))
    env.setdefault("GOVERNMENT_PROJECT_DRAFTS_ROOT", str(Path(env["GOVERNMENT_PROJECT_WORKSPACE_ROOT"]) / "proposal_drafts"))
    env["GOVERNMENT_PROJECT_LOG_ROOT"] = str(Path(args.log_dir))

    workspace_root = ensure_external_runtime_path(Path(env["GOVERNMENT_PROJECT_WORKSPACE_ROOT"]), "Invalid workspace path")
    runtime_home = ensure_external_runtime_path(Path(env["AGENT_BASE_HOME"]), "Invalid runtime home")
    host_base_dir = ensure_external_runtime_path(Path(env["AGENT_BASE_HOST_BASE_DIR"]), "Invalid host runtime home")
    knowledge_root = ensure_external_runtime_path(Path(env["AGENT_BASE_KNOWLEDGE_ROOT"]), "Invalid knowledge-base path")
    drafts_root = ensure_external_runtime_path(Path(env["GOVERNMENT_PROJECT_DRAFTS_ROOT"]), "Invalid proposal-drafts path")
    log_root = ensure_runtime_path(Path(env["GOVERNMENT_PROJECT_LOG_ROOT"]), "Invalid log directory", allow_inside_source=True)

    env["AGENT_BASE_HOME"] = str(runtime_home)
    env["DEER_FLOW_HOME"] = env["AGENT_BASE_HOME"]
    env["AGENT_BASE_HOST_BASE_DIR"] = str(host_base_dir)
    env["GOVERNMENT_PROJECT_WORKSPACE_ROOT"] = str(workspace_root)
    env["AGENT_BASE_KNOWLEDGE_ROOT"] = str(knowledge_root)
    env["GOVERNMENT_PROJECT_DRAFTS_ROOT"] = str(drafts_root)
    env["GOVERNMENT_PROJECT_LOG_ROOT"] = str(log_root)
    env.setdefault("AGENT_BASE_DB_PATH", str(runtime_home / "data" / "agent_base.db"))
    db_path = ensure_external_runtime_path(Path(env["AGENT_BASE_DB_PATH"]), "Invalid database path")
    env["AGENT_BASE_DB_PATH"] = str(db_path)

    workspace_root.mkdir(parents=True, exist_ok=True)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    knowledge_root.mkdir(parents=True, exist_ok=True)
    drafts_root.mkdir(parents=True, exist_ok=True)
    log_root.mkdir(parents=True, exist_ok=True)
    python_paths = [
        str(BACKEND_DIR),
        str(BACKEND_DIR / "packages" / "harness"),
    ]
    if env.get("PYTHONPATH"):
        python_paths.append(env["PYTHONPATH"])
    env["PYTHONPATH"] = os.pathsep.join(python_paths)
    env["AGENT_BASE_INTERNAL_GATEWAY_BASE_URL"] = f"http://{args.host}:{args.backend_port}"
    env["DEER_FLOW_INTERNAL_GATEWAY_BASE_URL"] = f"http://{args.host}:{args.backend_port}"
    env["DEER_FLOW_TRUSTED_ORIGINS"] = f"http://{args.host}:{args.frontend_port}"
    env["AGENT_BASE_TRUSTED_ORIGINS"] = f"http://{args.host}:{args.frontend_port}"
    env["NEXT_PUBLIC_LANGGRAPH_BASE_URL"] = f"http://{args.host}:{args.frontend_port}/api/langgraph"

    if args.network_proxy:
        env["HTTP_PROXY"] = args.network_proxy
        env["HTTPS_PROXY"] = args.network_proxy
        env["http_proxy"] = args.network_proxy
        env["https_proxy"] = args.network_proxy

    if not env.get("DEEPSEEK_API_KEY"):
        print("[warn] DEEPSEEK_API_KEY is not set. The configured DeepSeek V4 models will not be able to call DeepSeek.", flush=True)
        print("[hint] Create .env in the project root with: DEEPSEEK_API_KEY=your_api_key", flush=True)

    return env


def start_process(name: str, command: list[str], cwd: Path, env: dict[str, str], log_dir: Path) -> subprocess.Popen[str]:
    stdout_path = log_dir / f"{name}.stdout.log"
    stderr_path = log_dir / f"{name}.stderr.log"
    print(f"[start] {name}: {' '.join(command)}", flush=True)
    print(f"[log] {name} stdout: {stdout_path}", flush=True)
    print(f"[log] {name} stderr: {stderr_path}", flush=True)
    creationflags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
    stdout_file = stdout_path.open("w", encoding="utf-8", errors="replace")
    stderr_file = stderr_path.open("w", encoding="utf-8", errors="replace")
    process = subprocess.Popen(
        command,
        cwd=str(cwd),
        env=env,
        text=True,
        encoding="utf-8",
        errors="replace",
        stdout=stdout_file,
        stderr=stderr_file,
        creationflags=creationflags,
    )
    process._agent_base_name = name  # type: ignore[attr-defined]
    process._agent_base_log_handles = (stdout_file, stderr_file)  # type: ignore[attr-defined]
    process._agent_base_stdout_path = stdout_path  # type: ignore[attr-defined]
    process._agent_base_stderr_path = stderr_path  # type: ignore[attr-defined]
    return process


def terminate(processes: list[subprocess.Popen[str]]) -> None:
    for process in processes:
        if process.poll() is None:
            try:
                process.send_signal(signal.CTRL_BREAK_EVENT if os.name == "nt" else signal.SIGTERM)
            except Exception:
                process.terminate()
    time.sleep(2)
    for process in processes:
        if process.poll() is None:
            process.kill()
        for handle in getattr(process, "_agent_base_log_handles", ()):
            try:
                handle.close()
            except Exception:
                pass


def main() -> int:
    configure_console_encoding()
    args = parse_args()

    backend_python = ROOT_VENV_DIR / "Scripts" / "python.exe"
    next_bin = FRONTEND_NODE_MODULES_DIR / "next" / "dist" / "bin" / "next"
    ensure_file(backend_python, "Backend root venv python was not found")
    ensure_file(next_bin, "Frontend Next.js entry was not found. Run `make install` first")

    if is_port_open(args.host, args.backend_port):
        raise SystemExit(f"Backend port is already in use: {args.host}:{args.backend_port}")
    stop_existing_next_dev(FRONTEND_DIR, args.frontend_port)
    time.sleep(1)
    if is_port_open(args.host, args.frontend_port):
        raise SystemExit(f"Frontend port is already in use: {args.host}:{args.frontend_port}")

    env = build_env(args)
    log_dir = ensure_runtime_path(Path(env["GOVERNMENT_PROJECT_LOG_ROOT"]), "Invalid log directory", allow_inside_source=True)
    backend_cmd = [
        str(backend_python),
        "-m",
        "uvicorn",
        "app.gateway.app:app",
        "--host",
        args.host,
        "--port",
        str(args.backend_port),
    ]
    if args.reload:
        backend_cmd.append("--reload")

    frontend_cmd = [
        args.node,
        str(next_bin),
        "dev",
        "--webpack",
        "--hostname",
        args.host,
        "--port",
        str(args.frontend_port),
    ]

    processes: list[subprocess.Popen[str]] = []
    try:
        print(f"[info] backend reload: {'enabled' if args.reload else 'disabled'}", flush=True)
        processes.append(start_process("backend", backend_cmd, BACKEND_DIR, env, log_dir))
        if not wait_for_port("backend", processes[-1], args.host, args.backend_port, args.backend_timeout):
            return 1
        processes.append(start_process("frontend", frontend_cmd, FRONTEND_DIR, env, log_dir))
        if not wait_for_port("frontend", processes[-1], args.host, args.frontend_port, args.frontend_timeout):
            return 1
        if not ensure_processes_stable(processes):
            return 1
        if args.skip_warmup:
            print("[warmup] Skipped frontend route warmup.", flush=True)
        else:
            warm_frontend_routes(args)
        print("", flush=True)
        print(f"[ready] Web agent: http://{args.host}:{args.frontend_port}", flush=True)
        print(f"[ready] Backend:   http://{args.host}:{args.backend_port}/health", flush=True)
        print(f"[ready] Logs:      {log_dir}", flush=True)
        print("[info] Press Ctrl+C to stop both services.", flush=True)

        while True:
            for process in processes:
                code = process.poll()
                if code is not None:
                    print(f"[exit] A child process exited with code {code}. Stopping stack.", flush=True)
                    return code
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[stop] Stopping services...", flush=True)
        return 0
    finally:
        terminate(processes)


if __name__ == "__main__":
    raise SystemExit(main())
