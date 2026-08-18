@echo off
chcp 65001 >nul
rem ============================================================
rem  EduRAG 一键环境准备：首次运行自动建 venv + 装依赖 + 生成 .env
rem  幂等：环境已就绪时秒过，不影响日常启动速度
rem  被各 start_*.bat 调用（call），失败返回非 0
rem ============================================================
setlocal
cd /d "%~dp0backend"

rem ---- 已就绪则直接返回 ----
if exist ".venv\Scripts\python.exe" (
    if exist ".env" (
        exit /b 0
    )
)

echo.
echo [环境] 首次运行检测：开始准备 Python 虚拟环境与依赖（已装过则自动跳过）...
echo.

rem ---- 1. 找一个可用的系统 Python ----
set "PYTHON_CMD="
python --version >nul 2>&1 && set "PYTHON_CMD=python"
if not defined PYTHON_CMD (
    py -3 --version >nul 2>&1 && set "PYTHON_CMD=py -3"
)
if not defined PYTHON_CMD (
    echo [错误] 未检测到 Python，请先安装 Python 3.10 或更高版本：
    echo         https://www.python.org/downloads/
    echo         安装时请务必勾选 "Add Python to PATH"。
    pause
    exit /b 1
)

rem ---- 2. 创建虚拟环境 ----
if not exist ".venv\Scripts\python.exe" (
    echo [环境] 创建虚拟环境 .venv ...
    %PYTHON_CMD% -m venv .venv
    if errorlevel 1 (
        echo [错误] 虚拟环境创建失败，请确认 Python 版本 >= 3.10
        pause
        exit /b 1
    )
)

rem ---- 3. 安装依赖（默认国内镜像，失败自动回退官方源）----
echo [环境] 安装依赖，首次约需 2~5 分钟，请耐心等待 ...
set "PIP_INDEX=https://pypi.tuna.tsinghua.edu.cn/simple"
".venv\Scripts\python.exe" -m pip install --upgrade pip -i %PIP_INDEX% >nul 2>&1
".venv\Scripts\python.exe" -m pip install -r requirements.txt -i %PIP_INDEX%
if errorlevel 1 (
    echo [提示] 国内镜像安装失败，回退官方源重试 ...
    ".venv\Scripts\python.exe" -m pip install -r requirements.txt
    if errorlevel 1 (
        echo [错误] 依赖安装失败，请检查网络后重新运行本脚本
        pause
        exit /b 1
    )
)

rem ---- 4. 生成 .env（不存在时）----
if not exist ".env" (
    copy ".env.example" ".env" >nul
    echo [环境] 已从 .env.example 生成 .env（默认 Echo 离线模式，无需任何 Key）
)

echo [环境] 就绪：虚拟环境 + 依赖 + .env 均已准备
endlocal
exit /b 0
