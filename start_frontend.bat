@echo off
title Frontend static server (:5500)
cd /d "%~dp0frontend"

rem Auto setup env on first run (silent if ready); use python from venv
set "SETUP_SILENT=1"
call "%~dp0setup_env.bat"
if errorlevel 1 exit /b 1

set "PY=%~dp0backend\.venv\Scripts\python.exe"

echo Starting frontend static server: http://127.0.0.1:5500
echo Open http://127.0.0.1:5500 in your browser
echo Press Ctrl+C to stop, or close this window.
echo.
"%PY%" -m http.server 5500 --bind 127.0.0.1
pause
