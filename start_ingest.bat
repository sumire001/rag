@echo off
title MyProject 文档自动入库 (监听 data/import)
cd /d "%~dp0backend"

if not exist ".venv\Scripts\python.exe" (
    echo [错误] 未找到虚拟环境 backend\.venv\Scripts\python.exe
    echo 请先创建并安装依赖：
    echo   python -m venv .venv
    echo   .venv\Scripts\pip install -r requirements.txt
    pause
    exit /b 1
)

echo 正在启动文档目录监听...
echo 把文档放进 backend\data\import\ 即自动解析入库（约 5 秒一轮）
echo 成功文件归档到 data\imported\，失败文件移入 data\import_failed\
echo 按 Ctrl+C 停止，关闭窗口也会退出
echo.
.venv\Scripts\python.exe _watch_ingest.py
pause
