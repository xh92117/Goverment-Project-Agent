#!/usr/bin/env bash
# Stable Docker Compose entry point for the dedicated Linux server.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE_FILE="$REPO_ROOT/docker/docker-compose.server.yaml"
SERVER_STATE_ROOT="${AGENT_BASE_SERVER_STATE_ROOT:-/srv/agent-base}"

if ! command -v docker >/dev/null 2>&1; then
    echo "Docker is required." >&2
    exit 1
fi

if [ ! -f "$REPO_ROOT/.env" ]; then
    echo "Missing $REPO_ROOT/.env" >&2
    exit 1
fi
if [ ! -f "$REPO_ROOT/frontend/.env" ]; then
    echo "Missing $REPO_ROOT/frontend/.env" >&2
    exit 1
fi

export AGENT_BASE_HOME="${AGENT_BASE_HOME:-$SERVER_STATE_ROOT/data}"
export AGENT_BASE_KNOWLEDGE_ROOT="${AGENT_BASE_KNOWLEDGE_ROOT:-$SERVER_STATE_ROOT/public-knowledge}"
export AGENT_BASE_CONFIG_PATH="${AGENT_BASE_CONFIG_PATH:-$REPO_ROOT/config.yaml}"
export AGENT_BASE_EXTENSIONS_CONFIG_PATH="${AGENT_BASE_EXTENSIONS_CONFIG_PATH:-$REPO_ROOT/extensions_config.json}"
export AGENT_BASE_DOCKER_SOCKET="${AGENT_BASE_DOCKER_SOCKET:-/var/run/docker.sock}"
export AGENT_BASE_REPO_ROOT="$REPO_ROOT"

for required_file in "$AGENT_BASE_CONFIG_PATH" "$AGENT_BASE_EXTENSIONS_CONFIG_PATH"; do
    if [ ! -f "$required_file" ]; then
        echo "Missing required deployment file: $required_file" >&2
        exit 1
    fi
done

install -d -m 0750 "$AGENT_BASE_HOME" "$AGENT_BASE_KNOWLEDGE_ROOT"

container_env_value() {
    local container_name="$1"
    local env_name="$2"
    local env_lines
    env_lines="$(docker inspect "$container_name" --format '{{range .Config.Env}}{{println .}}{{end}}' 2>/dev/null || true)"
    printf '%s\n' "$env_lines" | sed -n "s/^${env_name}=//p" | head -n 1
}

generate_secret() {
    if command -v openssl >/dev/null 2>&1; then
        openssl rand -hex 32
    elif command -v python3 >/dev/null 2>&1; then
        python3 -c 'import secrets; print(secrets.token_hex(32))'
    else
        echo "openssl or python3 is required to generate deployment secrets." >&2
        return 1
    fi
}

load_or_create_secret() {
    local env_name="$1"
    local secret_file="$2"
    local container_name="$3"
    local value="${!env_name:-}"

    if [ -z "$value" ] && [ -s "$secret_file" ]; then
        value="$(<"$secret_file")"
    fi
    if [ -z "$value" ]; then
        value="$(container_env_value "$container_name" "$env_name")"
    fi
    if [ -z "$value" ]; then
        value="$(generate_secret)"
    fi

    umask 077
    printf '%s\n' "$value" > "$secret_file"
    chmod 600 "$secret_file"
    printf -v "$env_name" '%s' "$value"
    export "$env_name"
}

load_or_create_secret "BETTER_AUTH_SECRET" "$AGENT_BASE_HOME/.better-auth-secret" "agent-base-frontend"
load_or_create_secret "AGENT_BASE_INTERNAL_AUTH_TOKEN" "$AGENT_BASE_HOME/.internal-auth-token" "agent-base-gateway"

cd "$REPO_ROOT"
exec docker compose \
    --env-file "$REPO_ROOT/.env" \
    -p agent-base \
    -f "$COMPOSE_FILE" \
    "$@"
