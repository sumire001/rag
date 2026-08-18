@echo off
title 后端服务 (Flask + waitress)
cd /d "%~dp0backend"

rem 首次运行自动建 venv + 装依赖 + 生成 .env（已就绪则静默秒过）
set "SETUP_SILENT=1"
call "%~dp0setup_env.bat"
if errorlevel 1 exit /b 1

echo [清理] 释放 5000 端口残留进程（防止旧实例占着不放）
set "PORT_PIDS="
for /f "tokens=5" %%p in ('netstat -ano ^| findstr /R /C:":5000 .*LISTENING"') do (
    set "PORT_PIDS=!PORT_PIDS! %%p"
)
if defined PORT_PIDS (
    echo        待清理 PID:!PORT_PIDS!
    for %%p in (!PORT_PIDS!) do taskkill /F /PID %%p >nul 2>&1
    timeout /t 1 /nobreak >nul
) else (
    echo        端口空闲
)

echo 正在启动后端服务： http://127.0.0.1:5000
echo 按 Ctrl+C 停止，关闭窗口也会退出
echo.
.venv\Scripts\python.exe app.py
pause
