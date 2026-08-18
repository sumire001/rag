@echo off
title EduRAG Launcher (backend + frontend + feishu)
cd /d "%~dp0"

rem Auto setup env on first run (silent if ready)
set "SETUP_SILENT=1"
call "%~dp0setup_env.bat"
if errorlevel 1 exit /b 1

start "EduRAG Backend (5000)" start_backend.bat
start "EduRAG Frontend (5500)" start_frontend.bat
start "EduRAG Feishu bot" start_feishu.bat
echo Started backend, frontend and feishu in separate windows.
echo Frontend: http://127.0.0.1:5500
echo Backend:  http://127.0.0.1:5000
echo.
echo Notes:
echo  - Each service runs in its own window; closing this launcher is safe.
echo  - Feishu connects to Lark servers on startup, wait for its log window.
echo  - Press any key to close this launcher window.
pause >nul
