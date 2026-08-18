@echo off
title MyProject 启动器 (后端 + 前端 + 飞书)
cd /d "%~dp0"
start "MyProject 后端 (5000)" start_backend.bat
start "MyProject 前端 (5500)" start_frontend.bat
start "MyProject 飞书长连接" start_feishu.bat
echo 已分别在新窗口启动后端、前端和飞书通道。
echo 前端： http://127.0.0.1:5500
echo 后端： http://127.0.0.1:5000
echo.
echo 提示：
echo  - 每个服务都在独立窗口运行，关闭本窗口不会影响它们
echo  - 飞书长连接启动较慢（需连接飞书服务器鉴权），请到「MyProject 飞书长连接」窗口看日志
echo  - 按任意键关闭本启动器窗口
pause >nul
