@echo off
title MyProject 飞书机器人通道 (长连接)
cd /d "%~dp0backend"

if not exist ".venv\Scripts\python.exe" (
    echo [错误] 未找到虚拟环境 backend\.venv\Scripts\python.exe
    echo 请先创建并安装依赖：
    echo   python -m venv .venv
    echo   .venv\Scripts\pip install -r requirements.txt
    pause
    exit /b 1
)

echo 正在启动飞书长连接通道...
echo 请确保 .env 已配置 FEISHU_APP_ID / FEISHU_APP_SECRET
echo 按 Ctrl+C 停止，关闭窗口也会退出
echo.
.venv\Scripts\python.exe -m services.feishu.longpoll
pause
