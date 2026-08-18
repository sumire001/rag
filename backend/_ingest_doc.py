"""一次性脚本：把指定 Word 文档分块入库（documents + document_chunks，父子两级）。

用法（backend 目录下，venv）：
    .venv/Scripts/python.exe _ingest_doc.py
"""
from dotenv import load_dotenv

load_dotenv()

from config import BASE_DIR  # noqa: E402
from models import store  # noqa: E402
from services.documents import service as doc_service  # noqa: E402

SRC = str(BASE_DIR / "data" / "通用it知识.docx")


def main():
    import os

    if not os.path.exists(SRC):
        print("文件不存在:", SRC)
        return
    store.init_db()
    doc_id = "general-it-knowledge"
    old = store.get_document(doc_id)
    if old:
        store.delete_document(doc_id)
        print("已删除旧文档:", old["filename"], "旧分块数:", old.get("chunk_count"))
    row = doc_service.DocumentService.process_file(SRC, "通用it知识.docx", doc_id=doc_id)
    print("处理结果:", {k: row.get(k) for k in ("id", "filename", "file_type", "status", "error", "chunk_count")})

    # 统计两层切块数量
    parents = store.get_document_chunks(doc_id)  # 旧接口返回所有行
    # 用 store 直接查 parent/child 各自数量
    with store.get_conn() as conn:
        p = conn.execute(
            "SELECT COUNT(*) FROM document_chunks WHERE doc_id=? AND granularity='parent'",
            (doc_id,),
        ).fetchone()[0]
        c = conn.execute(
            "SELECT COUNT(*) FROM document_chunks WHERE doc_id=? AND granularity='child'",
            (doc_id,),
        ).fetchone()[0]
    print(f"分层: parent={p} child={c} total={p + c}")
    if parents:
        print("--- 第 1 个 parent 预览 ---")
        first = parents[0]
        print(f"[parent #{first['idx']}] {first['content'][:200]!r}")


if __name__ == "__main__":
    main()

