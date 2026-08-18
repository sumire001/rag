@echo off
title MyProject 前端服务 (静态服务器 :5500)
cd /d "%~dp0frontend"

set "PY=%~dp0backend\.venv\Scripts\python.exe"
if not exist "%PY%" (
    set "PY=python"
)

echo 正在启动前端静态服务器： http://127.0.0.1:5500
echo 请在浏览器打开： http://127.0.0.1:5500
echo 按 Ctrl+C 停止，关闭窗口也会退出
echo.
"%PY%" -m http.server 5500 --bind 127.0.0.1
pause
