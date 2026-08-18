@echo off
rem ============================================================
rem  EduRAG one-click environment setup:
rem  create venv + install dependencies + generate .env on first run
rem  Idempotent: returns immediately if environment is already ready
rem  Called by start_*.bat scripts (call), exit code 1 on failure
rem ============================================================
setlocal
cd /d "%~dp0backend"

rem ---- Already ready? Return immediately ----
if exist ".venv\Scripts\python.exe" (
    if exist ".env" (
        if not defined SETUP_SILENT (
            echo.
            echo [env] Ready: virtual environment and dependencies already installed.
            echo.
            timeout /t 3 >nul
        )
        exit /b 0
    )
)

echo.
echo [env] First run detected: preparing Python virtual environment...
echo.

rem ---- 1. Find a usable system Python ----
set "PYTHON_CMD="
python --version >nul 2>&1 && set "PYTHON_CMD=python"
if not defined PYTHON_CMD (
    py -3 --version >nul 2>&1 && set "PYTHON_CMD=py -3"
)
if not defined PYTHON_CMD (
    echo [ERROR] Python 3.10 or newer not found. Please install it from:
    echo         https://www.python.org/downloads/
    echo         and check "Add Python to PATH" during installation.
    pause
    exit /b 1
)

rem ---- 2. Create virtual environment ----
if not exist ".venv\Scripts\python.exe" (
    echo [env] Creating virtual environment .venv ...
    %PYTHON_CMD% -m venv .venv
    if errorlevel 1 (
        echo [ERROR] Failed to create venv. Python 3.10+ is required.
        pause
        exit /b 1
    )
)

rem ---- 3. Install dependencies (CN mirror first, fallback to official PyPI) ----
echo [env] Installing dependencies, first time takes 2-5 minutes...
set "PIP_INDEX=https://pypi.tuna.tsinghua.edu.cn/simple"
".venv\Scripts\python.exe" -m pip install --upgrade pip -i %PIP_INDEX% >nul 2>&1
".venv\Scripts\python.exe" -m pip install -r requirements.txt -i %PIP_INDEX%
if errorlevel 1 (
    echo [hint] Mirror install failed, retrying with official PyPI...
    ".venv\Scripts\python.exe" -m pip install -r requirements.txt
    if errorlevel 1 (
        echo [ERROR] Dependency install failed. Check your network and retry.
        pause
        exit /b 1
    )
)

rem ---- 4. Generate .env if missing ----
if not exist ".env" (
    copy ".env.example" ".env" >nul
    echo [env] Created .env from .env.example (default: echo offline mode, no key needed).
)

echo [env] Ready: venv + dependencies + .env all set.
endlocal
exit /b 0
