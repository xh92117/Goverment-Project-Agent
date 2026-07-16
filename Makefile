# Government Project Declaration Agent - Unified Development Environment

.PHONY: help config config-upgrade check ci ci-backend-light ci-backend-lint ci-frontend ci-docker-smoke live-smoke-chat live-smoke-subagent install setup doctor detect-thread-boundaries detect-blocking-io dev dev-daemon start start-daemon stop up down clean docker-init docker-start docker-stop docker-logs docker-logs-frontend docker-logs-gateway

BASH ?= bash
# Detect OS for Windows compatibility
ifeq ($(OS),Windows_NT)
    SHELL := cmd.exe
    PYTHON ?= python
    # Run repo shell scripts through Git Bash when Make is launched from cmd.exe / PowerShell.
    RUN_WITH_GIT_BASH = call scripts\run-with-git-bash.cmd
    BACKEND_UV_RUN = cd backend && set UV_PROJECT_ENVIRONMENT=../.venv&& uv run
    BACKEND_UV_SYNC = cd backend && set UV_PROJECT_ENVIRONMENT=../.venv&& uv sync
else
    PYTHON ?= python3
    RUN_WITH_GIT_BASH =
    BACKEND_UV_RUN = cd backend && UV_PROJECT_ENVIRONMENT=../.venv uv run
    BACKEND_UV_SYNC = cd backend && UV_PROJECT_ENVIRONMENT=../.venv uv sync
endif

help:
	@echo Government Project Declaration Agent Commands:
	@echo "  make setup           - Interactive setup wizard (recommended for new users)"
	@echo "  make doctor          - Check configuration and system requirements"
	@echo "  make config          - Generate local config files (aborts if config already exists)"
	@echo "  make config-upgrade  - Merge new fields from config.example.yaml into config.yaml"
	@echo "  make check           - Check if all required tools are installed"
	@echo "  make ci              - Run the local release-hardening baseline"
	@echo "  make ci-backend-light - Run lightweight backend regression"
	@echo "  make ci-frontend     - Run frontend lint/typecheck/tests/build"
	@echo "  make ci-docker-smoke - Validate Docker Compose production config"
	@echo "  make live-smoke-chat - Run UTF-8 live chat smoke test"
	@echo "  make live-smoke-subagent - Run live parent/subagent orchestration smoke test"
	@echo "  make detect-thread-boundaries - Inventory async/thread boundary points"
	@echo "  make detect-blocking-io        - Inventory blocking IO that may block the backend event loop"
	@echo "  make install         - Install all dependencies (frontend + backend + pre-commit hooks)"
	@echo "  make setup-sandbox   - Pre-pull sandbox container image (recommended)"
	@echo "  make dev             - Start all services in development mode (with hot-reloading)"
	@echo "  make dev-daemon      - Start dev services in background (daemon mode)"
	@echo "  make start           - Start all services in production mode (optimized, no hot-reloading)"
	@echo "  make start-daemon    - Start prod services in background (daemon mode)"
	@echo "  make stop            - Stop all running services"
	@echo "  make clean           - Clean up processes and temporary files"
	@echo ""
	@echo "Docker Production Commands:"
	@echo "  make up              - Build and start production Docker services (localhost:2026)"
	@echo "  make down            - Stop and remove production Docker containers"
	@echo ""
	@echo "Docker Development Commands:"
	@echo "  make docker-init     - Pull the sandbox image"
	@echo "  make docker-start    - Start Docker services (mode-aware from config.yaml, localhost:2026)"
	@echo "  make docker-stop     - Stop Docker development services"
	@echo "  make docker-logs     - View Docker development logs"
	@echo "  make docker-logs-frontend - View Docker frontend logs"
	@echo "  make docker-logs-gateway - View Docker gateway logs"

## Setup & Diagnosis
setup:
	@$(BACKEND_UV_RUN) python ../scripts/setup_wizard.py

doctor:
	@$(BACKEND_UV_RUN) python ../scripts/doctor.py

detect-thread-boundaries:
	@$(PYTHON) ./scripts/detect_thread_boundaries.py

detect-blocking-io:
	@$(MAKE) -C backend detect-blocking-io

config:
	@$(PYTHON) ./scripts/configure.py

config-upgrade:
	@$(RUN_WITH_GIT_BASH) ./scripts/config-upgrade.sh

# Check required tools
check:
	@$(PYTHON) ./scripts/check.py

ci: ci-backend-light ci-backend-lint ci-frontend ci-docker-smoke

ci-backend-light:
	@$(PYTHON) ./scripts/ci_backend_light.py

ci-backend-lint:
	@$(MAKE) -C backend lint

ci-frontend:
	@$(PYTHON) ./scripts/ci_frontend.py

ci-docker-smoke:
	@$(PYTHON) ./scripts/docker_smoke.py

live-smoke-chat:
	@$(BACKEND_UV_RUN) python ../scripts/live_agent_smoke.py --mode chat

live-smoke-subagent:
	@$(BACKEND_UV_RUN) python ../scripts/live_agent_smoke.py --mode subagent

# Install all dependencies
install:
	@echo ==================================================
	@echo Government Project Declaration Agent Installation
	@echo ==================================================
	@echo [1/3] Installing backend dependencies into .venv...
	@$(BACKEND_UV_SYNC) --quiet --link-mode copy
	@echo [2/3] Installing frontend dependencies into frontend/node_modules...
	@$(PYTHON) ./scripts/prepare_frontend_install.py
	@cd frontend && pnpm install --frozen-lockfile --reporter=append-only
	@echo [3/3] Installing local pre-commit hooks...
	@$(BACKEND_UV_RUN) --quiet --with pre-commit pre-commit install
	@echo Installation completed successfully.
	@echo Optional container sandbox command: make setup-sandbox

# Pre-pull sandbox Docker image (optional but recommended)
setup-sandbox:
	@$(RUN_WITH_GIT_BASH) ./scripts/setup-sandbox.sh

# Start all services in development mode (with hot-reloading)
dev:
	@$(PYTHON) ./scripts/check.py
	@$(RUN_WITH_GIT_BASH) ./scripts/serve.sh --dev

# Start all services in production mode (with optimizations)
start:
	@$(PYTHON) ./scripts/check.py
	@$(RUN_WITH_GIT_BASH) ./scripts/serve.sh --prod

# Start all services in daemon mode (background)
dev-daemon:
	@$(PYTHON) ./scripts/check.py
	@$(RUN_WITH_GIT_BASH) ./scripts/serve.sh --dev --daemon

# Start prod services in daemon mode (background)
start-daemon:
	@$(PYTHON) ./scripts/check.py
	@$(RUN_WITH_GIT_BASH) ./scripts/serve.sh --prod --daemon

# Stop all services
stop:
	@$(RUN_WITH_GIT_BASH) ./scripts/serve.sh --stop

# Clean up
clean: stop
	@echo "Cleaning up..."
	@-rm -rf backend/.agent-base 2>/dev/null || true
	@-rm -rf logs/*.log 2>/dev/null || true
	@echo "✓ Cleanup complete"

# ==========================================
# Docker Development Commands
# ==========================================

# Initialize Docker containers and install dependencies
docker-init:
	@$(RUN_WITH_GIT_BASH) ./scripts/docker.sh init

# Start Docker development environment
docker-start:
	@$(RUN_WITH_GIT_BASH) ./scripts/docker.sh start

# Stop Docker development environment
docker-stop:
	@$(RUN_WITH_GIT_BASH) ./scripts/docker.sh stop

# View Docker development logs
docker-logs:
	@$(RUN_WITH_GIT_BASH) ./scripts/docker.sh logs

# View Docker development logs
docker-logs-frontend:
	@$(RUN_WITH_GIT_BASH) ./scripts/docker.sh logs --frontend
docker-logs-gateway:
	@$(RUN_WITH_GIT_BASH) ./scripts/docker.sh logs --gateway

# ==========================================
# Production Docker Commands
# ==========================================

# Build and start production services
up:
	@$(RUN_WITH_GIT_BASH) ./scripts/deploy.sh

# Stop and remove production containers
down:
	@$(RUN_WITH_GIT_BASH) ./scripts/deploy.sh down
