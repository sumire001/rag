@echo off
chcp 65001 >nul
title 飞书机器人通道 (长连接)
cd /d "%~dp0backend"

rem 首次运行自动建 venv + 装依赖 + 生成 .env（已就绪则静默秒过）
set "SETUP_SILENT=1"
call "%~dp0setup_env.bat"
if errorlevel 1 exit /b 1

echo 正在启动飞书长连接通道...
echo 请确保 .env 已配置 FEISHU_APP_ID / FEISHU_APP_SECRET
echo 按 Ctrl+C 停止，关闭窗口也会退出
echo.
.venv\Scripts\python.exe -m services.feishu.longpoll
pause
