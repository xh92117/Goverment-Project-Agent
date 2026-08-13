"""Regression coverage for the Gateway-owned LangGraph API runtime."""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def _read(path: str) -> str:
    return (REPO_ROOT / path).read_text(encoding="utf-8")


def test_root_makefile_no_longer_exposes_transition_gateway_targets():
    makefile = _read("Makefile")

    assert "dev-pro" not in makefile
    assert "start-pro" not in makefile
    assert "dev-daemon-pro" not in makefile
    assert "start-daemon-pro" not in makefile
    assert "docker-start-pro" not in makefile
    assert "up-pro" not in makefile
    assert not re.search(r"serve\.sh .*--gateway", makefile)
    assert "docker.sh start --gateway" not in makefile
    assert "deploy.sh --gateway" not in makefile


def test_service_launchers_always_use_gateway_runtime():
    operational_files = {
        "scripts/serve.sh": _read("scripts/serve.sh"),
        "scripts/docker.sh": _read("scripts/docker.sh"),
        "scripts/deploy.sh": _read("scripts/deploy.sh"),
        "docker/docker-compose-dev.yaml": _read("docker/docker-compose-dev.yaml"),
        "docker/docker-compose.yaml": _read("docker/docker-compose.yaml"),
    }

    for path, content in operational_files.items():
        assert "start --gateway" not in content, path
        assert "deploy.sh --gateway" not in content, path
        assert "langgraph dev" not in content, path
        assert "LANGGRAPH_UPSTREAM" not in content, path
        assert "LANGGRAPH_REWRITE" not in content, path


def test_local_dev_gateway_reload_excludes_runtime_state_with_absolute_dirs():
    serve_sh = _read("scripts/serve.sh")

    assert 'export AGENT_BASE_PROJECT_ROOT="$REPO_ROOT"' in serve_sh
    assert 'BACKEND_RUNTIME_HOME="$REPO_ROOT/backend/.agent-base"' in serve_sh
    assert 'export AGENT_BASE_HOME="$BACKEND_RUNTIME_HOME"' in serve_sh
    assert 'mkdir -p "$AGENT_BASE_HOME" "$BACKEND_RUNTIME_HOME"' in serve_sh
    assert 'export DEER_FLOW_PROJECT_ROOT="$AGENT_BASE_PROJECT_ROOT"' not in serve_sh
    assert 'export DEER_FLOW_HOME="$AGENT_BASE_HOME"' not in serve_sh
    assert 'DEER_FLOW_HOME="$AGENT_BASE_HOME"' not in serve_sh
    assert "--reload-exclude='$AGENT_BASE_HOME'" in serve_sh
    assert "--reload-exclude='$BACKEND_RUNTIME_HOME'" in serve_sh
    assert "--reload-exclude='sandbox/'" not in serve_sh
    assert "--reload-exclude='.deer-flow/'" not in serve_sh


def test_local_dev_stop_helpers_use_agent_base_internal_names():
    serve_sh = _read("scripts/serve.sh")
    docker_sh = _read("scripts/docker.sh")
    deploy_sh = _read("scripts/deploy.sh")

    assert "AGENT_BASE_ROOTS" in serve_sh
    assert "_is_agent_base_pid" in serve_sh
    assert "DEERFLOW_ROOTS" not in serve_sh
    assert "_is_deerflow_pid" not in serve_sh
    assert 'export AGENT_BASE_ROOT="${DEER_FLOW_ROOT:-$PROJECT_ROOT}"' in docker_sh
    assert 'export DEER_FLOW_ROOT="${DEER_FLOW_ROOT:-$AGENT_BASE_ROOT}"' not in docker_sh
    assert 'export DEER_FLOW_HOME="$AGENT_BASE_HOME"' not in deploy_sh
    assert 'export DEER_FLOW_CONFIG_PATH="$AGENT_BASE_CONFIG_PATH"' not in deploy_sh
    assert 'export DEER_FLOW_EXTENSIONS_CONFIG_PATH="$AGENT_BASE_EXTENSIONS_CONFIG_PATH"' not in deploy_sh
    assert 'export DEER_FLOW_REPO_ROOT="${DEER_FLOW_REPO_ROOT:-$AGENT_BASE_REPO_ROOT}"' not in deploy_sh
    assert 'export DEER_FLOW_DOCKER_SOCKET="${DEER_FLOW_DOCKER_SOCKET:-$AGENT_BASE_DOCKER_SOCKET}"' not in deploy_sh
    assert 'export DEER_FLOW_INTERNAL_AUTH_TOKEN="$AGENT_BASE_INTERNAL_AUTH_TOKEN"' not in deploy_sh


def test_frontend_compose_uses_agent_base_internal_gateway_url_only():
    for path in ("docker/docker-compose.yaml", "docker/docker-compose-dev.yaml"):
        content = _read(path)
        frontend_section = content.split("container_name: agent-base-frontend", 1)[1].split("networks:", 1)[0]

        assert "AGENT_BASE_INTERNAL_GATEWAY_BASE_URL=http://gateway:8001" in frontend_section
        assert "DEER_FLOW_INTERNAL_GATEWAY_BASE_URL=http://gateway:8001" not in frontend_section


def test_frontend_compose_uses_agent_base_trusted_origins_only():
    for path in ("docker/docker-compose.yaml", "docker/docker-compose-dev.yaml"):
        content = _read(path)
        frontend_section = content.split("container_name: agent-base-frontend", 1)[1].split("networks:", 1)[0]

        assert "AGENT_BASE_TRUSTED_ORIGINS=" in frontend_section
        assert "DEER_FLOW_TRUSTED_ORIGINS=" not in frontend_section


def test_gateway_compose_uses_agent_base_channel_urls_only():
    for path in ("docker/docker-compose.yaml", "docker/docker-compose-dev.yaml"):
        content = _read(path)
        gateway_section = content.split("container_name: agent-base-gateway", 1)[1].split("env_file:", 1)[0]

        assert "AGENT_BASE_CHANNELS_LANGGRAPH_URL=" in gateway_section
        assert "AGENT_BASE_CHANNELS_GATEWAY_URL=" in gateway_section
        assert "DEER_FLOW_CHANNELS_LANGGRAPH_URL=" not in gateway_section
        assert "DEER_FLOW_CHANNELS_GATEWAY_URL=" not in gateway_section


def test_gateway_compose_uses_agent_base_internal_auth_token_only():
    for path in ("docker/docker-compose.yaml", "docker/docker-compose-dev.yaml"):
        content = _read(path)
        gateway_section = content.split("container_name: agent-base-gateway", 1)[1].split("env_file:", 1)[0]

        assert "AGENT_BASE_INTERNAL_AUTH_TOKEN=" in gateway_section
        assert "DEER_FLOW_INTERNAL_AUTH_TOKEN=" not in gateway_section


def test_production_compose_enables_fail_closed_multi_user_mode_by_default():
    content = _read("docker/docker-compose.yaml")
    gateway_section = content.split("container_name: agent-base-gateway", 1)[1].split("env_file:", 1)[0]

    assert "GATEWAY_ENABLE_LOCAL_AUTH=${GATEWAY_ENABLE_LOCAL_AUTH:-true}" in gateway_section
    assert "AGENT_BASE_STRICT_USER_CONTEXT=${AGENT_BASE_STRICT_USER_CONTEXT:-true}" in gateway_section


def test_provisioner_compose_exposes_user_scoped_host_root():
    content = _read("docker/docker-compose.yaml")
    provisioner_section = content.split("container_name: agent-base-provisioner", 1)[1].split("env_file:", 1)[0]

    assert "USERS_HOST_PATH=${AGENT_BASE_HOME}/users" in provisioner_section


def test_gateway_compose_uses_agent_base_runtime_paths_only():
    legacy_runtime_envs = (
        "DEER_FLOW_PROJECT_ROOT=",
        "DEER_FLOW_HOME=",
        "DEER_FLOW_CONFIG_PATH=",
        "DEER_FLOW_EXTENSIONS_CONFIG_PATH=",
        "DEER_FLOW_SKILLS_PATH=",
    )

    for path in ("docker/docker-compose.yaml", "docker/docker-compose-dev.yaml"):
        content = _read(path)
        gateway_section = content.split("container_name: agent-base-gateway", 1)[1].split("env_file:", 1)[0]

        assert "AGENT_BASE_PROJECT_ROOT=" in gateway_section
        assert "AGENT_BASE_HOME=" in gateway_section
        assert "AGENT_BASE_CONFIG_PATH=" in gateway_section
        assert "AGENT_BASE_EXTENSIONS_CONFIG_PATH=" in gateway_section
        assert "AGENT_BASE_SKILLS_PATH=" in gateway_section
        for legacy_env in legacy_runtime_envs:
            assert legacy_env not in gateway_section


def test_gateway_compose_uses_agent_base_sandbox_paths_only():
    legacy_sandbox_envs = (
        "DEER_FLOW_HOST_BASE_DIR=",
        "DEER_FLOW_HOST_SKILLS_PATH=",
        "DEER_FLOW_SANDBOX_HOST=",
    )

    for path in ("docker/docker-compose.yaml", "docker/docker-compose-dev.yaml"):
        content = _read(path)
        gateway_section = content.split("container_name: agent-base-gateway", 1)[1].split("env_file:", 1)[0]

        assert "AGENT_BASE_HOST_BASE_DIR=" in gateway_section
        assert "AGENT_BASE_HOST_SKILLS_PATH=" in gateway_section
        assert "AGENT_BASE_SANDBOX_HOST=" in gateway_section
        for legacy_env in legacy_sandbox_envs:
            assert legacy_env not in gateway_section


def test_aio_sandbox_default_container_prefix_is_agent_base():
    provider_source = _read("backend/packages/harness/deerflow/community/aio_sandbox/aio_sandbox_provider.py")

    assert 'DEFAULT_CONTAINER_PREFIX = "agent-base-sandbox"' in provider_source
    assert 'DEFAULT_CONTAINER_PREFIX = "deer-flow-sandbox"' not in provider_source


def test_backend_container_only_exposes_gateway_port():
    dockerfile = _read("backend/Dockerfile")

    assert not re.search(r"^EXPOSE\s+.*\b2024\b", dockerfile, re.M)
    assert "langgraph: 2024" not in dockerfile
    assert re.search(r"^EXPOSE\s+8001\b", dockerfile, re.M)


def test_root_makefile_clean_does_not_reference_langgraph_server_cache():
    makefile = _read("Makefile")

    assert ".langgraph_api" not in makefile


def test_nginx_routes_official_langgraph_prefix_to_gateway_api():
    for path in ("docker/nginx/nginx.local.conf", "docker/nginx/nginx.conf"):
        content = _read(path)

        assert "/api/langgraph-compat" not in content
        assert "proxy_pass http://langgraph" not in content
        assert "rewrite ^/api/langgraph/(.*) /api/$1 break;" in content
        assert "proxy_pass http://gateway" in content or "proxy_pass http://$gateway_upstream" in content


def test_nginx_defers_cors_to_gateway_allowlist():
    for path in ("docker/nginx/nginx.local.conf", "docker/nginx/nginx.conf"):
        content = _read(path)

        assert "Access-Control-Allow-Origin" not in content
        assert "Access-Control-Allow-Methods" not in content
        assert "Access-Control-Allow-Headers" not in content
        assert "Access-Control-Allow-Credentials" not in content
        assert "proxy_hide_header 'Access-Control-Allow-" not in content
        assert "if ($request_method = 'OPTIONS')" not in content


def test_gateway_cors_configuration_uses_gateway_allowlist():
    gateway_config = _read("backend/app/gateway/config.py")
    gateway_app = _read("backend/app/gateway/app.py")
    csrf_middleware = _read("backend/app/gateway/csrf_middleware.py")

    assert not re.search(r"(?<!GATEWAY_)[\"']CORS_ORIGINS[\"']", gateway_config)
    assert "cors_origins" not in gateway_config
    assert "get_configured_cors_origins" in gateway_app
    assert "GATEWAY_CORS_ORIGINS" in csrf_middleware


def test_frontend_rewrites_langgraph_prefix_to_gateway():
    next_config = _read("frontend/next.config.js")
    api_client = _read("frontend/src/shared/api/client.ts")
    api_config = _read("frontend/src/shared/api/config.ts")

    assert "DEER_FLOW_INTERNAL_LANGGRAPH_BASE_URL" not in next_config
    assert "http://127.0.0.1:2024" not in next_config
    assert "langgraph-compat" not in api_client
    assert "langgraph-compat" not in api_config


def test_smoke_test_docs_do_not_expect_standalone_langgraph_server():
    smoke_paths = [
        ".agent/skills/smoke-test/SKILL.md",
        ".agent/skills/smoke-test/references/SOP.md",
        ".agent/skills/smoke-test/references/troubleshooting.md",
        ".agent/skills/smoke-test/scripts/check_local_env.sh",
        ".agent/skills/smoke-test/scripts/deploy_local.sh",
        ".agent/skills/smoke-test/scripts/health_check.sh",
        ".agent/skills/smoke-test/templates/report.local.template.md",
        ".agent/skills/smoke-test/templates/report.docker.template.md",
    ]
    smoke_files = {path: _read(path) for path in smoke_paths if (REPO_ROOT / path).exists()}

    if not smoke_files:
        assert not (REPO_ROOT / ".agent/skills/smoke-test").exists()
        return

    for path, content in smoke_files.items():
        assert "localhost:2024" not in content, path
        assert "127.0.0.1:2024" not in content, path
        assert "deer-flow-langgraph" not in content, path
        assert "langgraph.log" not in content, path
        assert "LangGraph service" not in content, path
        assert "langgraph dev" not in content, path


def test_gateway_runtime_docs_do_not_reference_transition_modes():
    docs = {
        "backend/docs/AUTH_UPGRADE.md": _read("backend/docs/AUTH_UPGRADE.md"),
        "backend/docs/AUTH_TEST_DOCKER_GAP.md": _read("backend/docs/AUTH_TEST_DOCKER_GAP.md"),
    }

    for path, content in docs.items():
        assert "make dev-pro" not in content, path
        assert "./scripts/deploy.sh --gateway" not in content, path
        assert "docker compose --profile gateway" not in content, path
        assert "`/api/langgraph/*` → LangGraph" not in content, path
