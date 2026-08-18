@echo off
title Feishu bot channel (long connection)
cd /d "%~dp0backend"

rem Auto setup env on first run (silent if ready)
set "SETUP_SILENT=1"
call "%~dp0setup_env.bat"
if errorlevel 1 exit /b 1

echo Starting Feishu long-connection channel...
echo Make sure FEISHU_APP_ID / FEISHU_APP_SECRET are set in backend/.env
echo Press Ctrl+C to stop, or close this window.
echo.
.venv\Scripts\python.exe -m services.feishu.longpoll
pause
