"""目录批量导入：把指定目录下的文档自动解析入库。

用法场景：
- 一次性批量导入：backend/_ingest_dir.py [目录]
- 常驻自动监听：backend/_watch_ingest.py [间隔秒]

目录约定（均在 backend/data/ 下）：
    import/          投放目录：把文档放进来即可被处理
    imported/        归档目录：已成功入库的文件移动到这里
    import_failed/   失败目录：解析失败 / 不支持的格式移动到这里

特性：
- 幂等：按文件内容 md5 生成稳定 doc_id，同名同内容的文件重复放置会跳过（仅归档）；
- 入库后自动重建 RAG 内存索引（rag_service.rebuild_index），问答立即生效；
- 跳过 Office 临时文件（~$）、隐藏文件、*.tmp / *.part 等未写完文件。
"""
import hashlib
import logging
import os
import shutil
import time
from pathlib import Path

from config import BASE_DIR
from models import store
from services.documents import service as doc_service
from services.rag import service as rag_service

logger = logging.getLogger("documents.ingester")

# 默认目录（相对 backend/）
INGEST_DIR = Path(BASE_DIR) / "data" / "import"
IMPORTED_DIR = Path(BASE_DIR) / "data" / "imported"
FAILED_DIR = Path(BASE_DIR) / "data" / "import_failed"

# 跳过规则：Office 锁文件 / 隐藏文件 / 未下载完的临时文件
_SKIP_PREFIXES = ("~$", ".")
_SKIP_SUFFIXES = (".tmp", ".part", ".crdownload", ".download")


def _stable_doc_id(src_path: str) -> str:
    """按文件内容 md5 生成稳定 doc_id：内容不变则 id 不变，天然幂等。"""
    h = hashlib.md5()
    with open(src_path, "rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return "ingest-" + h.hexdigest()[:16]


def _should_skip(name: str) -> bool:
    low = name.lower()
    if name.startswith(_SKIP_PREFIXES) or low.endswith(_SKIP_SUFFIXES):
        return True
    return False


def _ensure_dirs() -> None:
    for d in (INGEST_DIR, IMPORTED_DIR, FAILED_DIR):
        d.mkdir(parents=True, exist_ok=True)


def scan_and_ingest(input_dir=None, rebuild: bool = True, move: bool = True) -> dict:
    """扫描 input_dir（默认 data/import）下所有支持的文档并入库。

    参数：
        input_dir: 要扫描的目录；缺省用 INGEST_DIR
        rebuild:   入库后是否重建 RAG 索引（默认 True）
        move:      处理后是否移动文件到 imported / failed（默认 True）

    返回统计：{scanned, imported, skipped, unsupported, failed, errors}
    """
    input_dir = Path(input_dir or INGEST_DIR)
    if not input_dir.exists():
        return {"scanned": 0, "imported": 0, "skipped": 0, "unsupported": 0, "failed": 0, "errors": []}

    _ensure_dirs()
    stats = {"scanned": 0, "imported": 0, "skipped": 0, "unsupported": 0, "failed": 0, "errors": []}
    files = sorted(
        p for p in input_dir.rglob("*")
        if p.is_file() and not _should_skip(p.name)
    )

    for src in files:
        stats["scanned"] += 1
        filename = src.name

        if not doc_service.DocumentService.allowed_ext(filename):
            stats["unsupported"] += 1
            stats["errors"].append(f"{filename}: 不支持的文件类型")
            if move:
                _move(src, FAILED_DIR)
            continue

        doc_id = _stable_doc_id(str(src))
        if store.get_document(doc_id):
            # 内容相同的文档已入库过：跳过并归档（幂等）
            stats["skipped"] += 1
            if move:
                _move(src, IMPORTED_DIR)
            continue

        try:
            result = doc_service.DocumentService.process_file(str(src), filename, doc_id=doc_id)
        except Exception as e:
            logger.exception("文档入库失败 %s", filename)
            stats["failed"] += 1
            stats["errors"].append(f"{filename}: {e}")
            if move:
                _move(src, FAILED_DIR)
            continue

        if result.get("status") == "error":
            stats["failed"] += 1
            stats["errors"].append(f"{filename}: {result.get('error')}")
            if move:
                _move(src, FAILED_DIR)
            continue

        stats["imported"] += 1
        logger.info("已入库 %s（%d 分块，%s）", filename, result.get("chunk_count", 0), doc_id)
        if move:
            _move(src, IMPORTED_DIR)

    if stats["imported"] and rebuild:
        try:
            rag_service.rebuild_index()
            logger.info("已重建 RAG 索引")
        except Exception:
            logger.exception("重建 RAG 索引失败")

    return stats


def _move(src: Path, dest_dir: Path) -> None:
    """移动到目标目录；目标同名文件已存在时加时间戳后缀，避免覆盖。"""
    dest_dir.mkdir(parents=True, exist_ok=True)
    target = dest_dir / src.name
    if target.exists():
        stem, ext = os.path.splitext(src.name)
        target = dest_dir / f"{stem}-{int(time.time())}{ext}"
    shutil.move(str(src), str(target))
