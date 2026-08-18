@echo off
title Document auto-ingest (watch data/import)
cd /d "%~dp0backend"

rem Auto setup env on first run (silent if ready)
set "SETUP_SILENT=1"
call "%~dp0setup_env.bat"
if errorlevel 1 exit /b 1

echo Starting document folder watcher...
echo Drop documents into backend\data\import\ and they will be auto-ingested (~5s cycle)
echo Success files move to data\imported\, failed files to data\import_failed\
echo Press Ctrl+C to stop, or close this window.
echo.
.venv\Scripts\python.exe _watch_ingest.py
pause
