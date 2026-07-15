UV_PROJECT_ENVIRONMENT ?= ../.venv
BACKEND_UV = UV_PROJECT_ENVIRONMENT=$(UV_PROJECT_ENVIRONMENT) uv

install:
	$(BACKEND_UV) sync

dev:
	PYTHONPATH=. PYTHONIOENCODING=utf-8 PYTHONUTF8=1 $(BACKEND_UV) run uvicorn app.gateway.app:app --host 0.0.0.0 --port 8001 --reload

gateway:
	PYTHONPATH=. PYTHONIOENCODING=utf-8 PYTHONUTF8=1 $(BACKEND_UV) run uvicorn app.gateway.app:app --host 0.0.0.0 --port 8001

test:
	PYTHONPATH=. PYTHONIOENCODING=utf-8 PYTHONUTF8=1 $(BACKEND_UV) run pytest tests/ -v

test-blocking-io:
	PYTHONPATH=. PYTHONIOENCODING=utf-8 PYTHONUTF8=1 $(BACKEND_UV) run pytest tests/blocking_io -q --tb=short

lint:
	uvx ruff check .
	uvx ruff format --check .

format:
	uvx ruff check . --fix && uvx ruff format .

detect-blocking-io:
	@PYTHONPATH=. PYTHONIOENCODING=utf-8 PYTHONUTF8=1 $(BACKEND_UV) run python ../scripts/detect_blocking_io_static.py --output ../.agent-base/blocking-io-findings.json
