"""目录自动监听：每隔 N 秒扫描 data/import，新放入的文档自动解析入库。

用法（backend 目录下，venv）：
    .venv/Scripts/python.exe _watch_ingest.py [间隔秒]   默认 5 秒

启动后先执行一次全量扫描，之后进入轮询；Ctrl+C 退出。
与 `_ingest_dir.py` 的区别：本脚本常驻运行，适合"放文件即入库"的实时场景。
"""
import logging
import sys
import time

from dotenv import load_dotenv

load_dotenv()

from models import store  # noqa: E402
from services.documents import ingester  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("watch_ingest")


def main():
    store.init_db()
    interval = int(sys.argv[1]) if len(sys.argv) > 1 else 5
    interval = max(1, interval)

    logger.info("目录监听启动：%s（每 %d 秒扫描一次）", ingester.INGEST_DIR, interval)
    logger.info("把文档放进上面的目录即自动入库；按 Ctrl+C 停止")

    while True:
        try:
            stats = ingester.scan_and_ingest()
            if stats["scanned"]:
                logger.info("本轮扫描：%s", stats)
        except Exception:
            logger.exception("扫描异常（下一轮重试）")
        time.sleep(interval)


if __name__ == "__main__":
    main()
