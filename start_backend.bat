@echo off
title Backend (Flask + waitress)
cd /d "%~dp0backend"

rem Auto setup env on first run (silent if ready)
set "SETUP_SILENT=1"
call "%~dp0setup_env.bat"
if errorlevel 1 exit /b 1

echo [cleanup] Releasing port 5000 if occupied by a stale process...
set "PORT_PIDS="
for /f "tokens=5" %%p in ('netstat -ano ^| findstr /R /C:":5000 .*LISTENING"') do (
    set "PORT_PIDS=!PORT_PIDS! %%p"
)
if defined PORT_PIDS (
    echo        Killing stale PID:!PORT_PIDS!
    for %%p in (!PORT_PIDS!) do taskkill /F /PID %%p >nul 2>&1
    timeout /t 1 /nobreak >nul
) else (
    echo        Port is free
)

echo Starting backend: http://127.0.0.1:5000
echo Press Ctrl+C to stop, or close this window.
echo.
.venv\Scripts\python.exe app.py
pause
