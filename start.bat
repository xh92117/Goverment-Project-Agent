@echo off
setlocal EnableExtensions EnableDelayedExpansion
chcp 65001 >nul
cd /d "%~dp0"

set "PNPM_VERSION=10.26.2"
set "DEPENDENCY_STATE_DIR=.tools\dependency-state"

echo ================================================
echo Government Project Declaration Agent - Start
echo ================================================

call :check_node
if errorlevel 1 exit /b 1

echo [check] Checking project dependencies...
call :check_project_dependencies
if not errorlevel 1 (
    echo [ok] Project dependencies are ready.
    call :save_dependency_state >nul 2>&1
    goto :launch
)

echo [info] Missing or outdated project dependencies detected.
call :ensure_install_tools
if errorlevel 1 exit /b 1

call :install_project_dependencies
if errorlevel 1 (
    echo [error] Dependency installation failed.
    echo [hint] If a proxy is configured, verify that its HTTP/Mixed port is listening.
    exit /b 1
)

echo [check] Verifying installed dependencies...
call :check_project_dependencies
if errorlevel 1 (
    echo [error] Dependencies are still incomplete after installation.
    exit /b 1
)
echo [ok] Dependency installation completed.

:launch
echo [start] Starting backend and frontend...
".venv\Scripts\python.exe" "start_web_agent.py" %*
set "START_EXIT=!ERRORLEVEL!"
if not "!START_EXIT!"=="0" echo [error] Application exited with code !START_EXIT!.
exit /b !START_EXIT!

:check_node
where node >nul 2>&1
if errorlevel 1 (
    echo [error] Node.js was not found. Install Node.js 22 LTS or newer, then rerun start.bat.
    exit /b 1
)

set "NODE_MAJOR="
for /f "tokens=1 delims=." %%V in ('node --version 2^>nul') do set "NODE_MAJOR=%%V"
set "NODE_MAJOR=!NODE_MAJOR:v=!"
if not defined NODE_MAJOR (
    echo [error] Unable to determine the Node.js version.
    exit /b 1
)
if !NODE_MAJOR! LSS 22 (
    echo [error] Node.js !NODE_MAJOR! is too old. Install Node.js 22 LTS or newer.
    exit /b 1
)
echo [ok] Node.js detected: v!NODE_MAJOR!
exit /b 0

:ensure_install_tools
where uv >nul 2>&1
if errorlevel 1 call :install_uv
if errorlevel 1 exit /b 1

where pnpm >nul 2>&1
if errorlevel 1 call :install_pnpm
if errorlevel 1 exit /b 1

for /f "delims=" %%V in ('uv --version 2^>nul') do echo [ok] %%V
for /f "delims=" %%V in ('pnpm --version 2^>nul') do echo [ok] pnpm %%V
exit /b 0

:install_uv
echo [install] uv was not found; attempting installation with Python 3.12...
where py >nul 2>&1
if not errorlevel 1 (
    py -3.12 -m pip install --user --upgrade uv
    if not errorlevel 1 (
        for /f "delims=" %%D in ('py -3.12 -c "import site; print(site.getuserbase())" 2^>nul') do set "PATH=%%D\Scripts;!PATH!"
    )
)

where uv >nul 2>&1
if not errorlevel 1 exit /b 0

where python >nul 2>&1
if not errorlevel 1 (
    python -m pip install --user --upgrade uv
    if not errorlevel 1 (
        for /f "delims=" %%D in ('python -c "import site; print(site.getuserbase())" 2^>nul') do set "PATH=%%D\Scripts;!PATH!"
    )
)

where uv >nul 2>&1
if errorlevel 1 (
    echo [error] uv could not be installed automatically. Install uv and ensure it is on PATH.
    exit /b 1
)
exit /b 0

:install_pnpm
echo [install] pnpm was not found; attempting Corepack setup...
where corepack >nul 2>&1
if not errorlevel 1 (
    call corepack enable >nul 2>&1
    call corepack prepare pnpm@%PNPM_VERSION% --activate
)

where pnpm >nul 2>&1
if not errorlevel 1 exit /b 0

where npm >nul 2>&1
if not errorlevel 1 (
    echo [install] Corepack setup was unavailable; installing pnpm with npm...
    call npm install --global pnpm@%PNPM_VERSION%
)

where pnpm >nul 2>&1
if errorlevel 1 (
    echo [error] pnpm could not be installed automatically. Install pnpm %PNPM_VERSION% and ensure it is on PATH.
    exit /b 1
)
exit /b 0

:check_project_dependencies
if not exist ".venv\Scripts\python.exe" exit /b 1
if not exist "frontend\node_modules\next\dist\bin\next" exit /b 1

if exist "%DEPENDENCY_STATE_DIR%\installed.flag" (
    call :dependency_state_matches
    if errorlevel 1 exit /b 1
)

pushd backend >nul
"..\.venv\Scripts\python.exe" -c "from PIL import Image; from app.gateway.app import app" >nul 2>&1
set "BACKEND_CHECK=!ERRORLEVEL!"
popd >nul
if not "!BACKEND_CHECK!"=="0" exit /b 1

node "frontend\node_modules\next\dist\bin\next" --version >nul 2>&1
if errorlevel 1 exit /b 1
exit /b 0

:dependency_state_matches
if not exist "%DEPENDENCY_STATE_DIR%\backend-uv.lock" exit /b 1
if not exist "%DEPENDENCY_STATE_DIR%\backend-pyproject.toml" exit /b 1
if not exist "%DEPENDENCY_STATE_DIR%\harness-pyproject.toml" exit /b 1
if not exist "%DEPENDENCY_STATE_DIR%\frontend-pnpm-lock.yaml" exit /b 1
if not exist "%DEPENDENCY_STATE_DIR%\frontend-package.json" exit /b 1
if not exist "%DEPENDENCY_STATE_DIR%\frontend-pnpm-workspace.yaml" exit /b 1

fc /b "backend\uv.lock" "%DEPENDENCY_STATE_DIR%\backend-uv.lock" >nul 2>&1 || exit /b 1
fc /b "backend\pyproject.toml" "%DEPENDENCY_STATE_DIR%\backend-pyproject.toml" >nul 2>&1 || exit /b 1
fc /b "backend\packages\harness\pyproject.toml" "%DEPENDENCY_STATE_DIR%\harness-pyproject.toml" >nul 2>&1 || exit /b 1
fc /b "frontend\pnpm-lock.yaml" "%DEPENDENCY_STATE_DIR%\frontend-pnpm-lock.yaml" >nul 2>&1 || exit /b 1
fc /b "frontend\package.json" "%DEPENDENCY_STATE_DIR%\frontend-package.json" >nul 2>&1 || exit /b 1
fc /b "frontend\pnpm-workspace.yaml" "%DEPENDENCY_STATE_DIR%\frontend-pnpm-workspace.yaml" >nul 2>&1 || exit /b 1
exit /b 0

:install_project_dependencies
echo [install] Synchronizing backend dependencies...
pushd backend >nul
set "UV_PROJECT_ENVIRONMENT=..\.venv"
uv sync --locked --link-mode copy
if errorlevel 1 (
    set "INSTALL_EXIT=!ERRORLEVEL!"
    set "UV_PROJECT_ENVIRONMENT="
    popd >nul
    exit /b !INSTALL_EXIT!
)

uv pip install --link-mode copy --python "..\.venv\Scripts\python.exe" --editable ".\packages\harness[deepseek,openai,mcp,search,documents]"
if errorlevel 1 (
    set "INSTALL_EXIT=!ERRORLEVEL!"
    set "UV_PROJECT_ENVIRONMENT="
    popd >nul
    exit /b !INSTALL_EXIT!
)
set "UV_PROJECT_ENVIRONMENT="
popd >nul

".venv\Scripts\python.exe" "scripts\prepare_frontend_install.py"
if errorlevel 1 exit /b !ERRORLEVEL!

echo [install] Synchronizing frontend dependencies...
pushd frontend >nul
call pnpm install --frozen-lockfile --reporter=append-only
if errorlevel 1 (
    set "INSTALL_EXIT=!ERRORLEVEL!"
    popd >nul
    exit /b !INSTALL_EXIT!
)
popd >nul

call :save_dependency_state
exit /b !ERRORLEVEL!

:save_dependency_state
if not exist "%DEPENDENCY_STATE_DIR%" mkdir "%DEPENDENCY_STATE_DIR%" >nul 2>&1
if errorlevel 1 exit /b 1

copy /y "backend\uv.lock" "%DEPENDENCY_STATE_DIR%\backend-uv.lock" >nul || exit /b 1
copy /y "backend\pyproject.toml" "%DEPENDENCY_STATE_DIR%\backend-pyproject.toml" >nul || exit /b 1
copy /y "backend\packages\harness\pyproject.toml" "%DEPENDENCY_STATE_DIR%\harness-pyproject.toml" >nul || exit /b 1
copy /y "frontend\pnpm-lock.yaml" "%DEPENDENCY_STATE_DIR%\frontend-pnpm-lock.yaml" >nul || exit /b 1
copy /y "frontend\package.json" "%DEPENDENCY_STATE_DIR%\frontend-package.json" >nul || exit /b 1
copy /y "frontend\pnpm-workspace.yaml" "%DEPENDENCY_STATE_DIR%\frontend-pnpm-workspace.yaml" >nul || exit /b 1
> "%DEPENDENCY_STATE_DIR%\installed.flag" echo ready
exit /b 0
