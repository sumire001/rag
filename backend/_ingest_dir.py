"""一次性批量导入：把 data/import 目录下的文档全部解析入库（处理完自动移走）。

用法（backend 目录下，venv）：
    .venv/Scripts/python.exe _ingest_dir.py [目录]

不带参数默认扫描 backend/data/import/。
重复运行安全：已入库的同名同内容文件会自动跳过（幂等）。
"""
import logging
import sys

from dotenv import load_dotenv

load_dotenv()

from models import store  # noqa: E402
from services.documents import ingester  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


def main():
    store.init_db()
    target = sys.argv[1] if len(sys.argv) > 1 else str(ingester.INGEST_DIR)
    print(f"扫描目录：{target}")
    stats = ingester.scan_and_ingest(target)
    print("导入完成：", stats)
    if stats["imported"]:
        print(f"已入库文件归档至：{ingester.IMPORTED_DIR}")
    if stats["failed"] or stats["unsupported"]:
        print(f"失败/不支持的已移至：{ingester.FAILED_DIR}")
        for e in stats["errors"]:
            print("  -", e)


if __name__ == "__main__":
    main()
