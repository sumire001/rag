"""文档处理服务：保存文件 -> 抽取 -> 切片 -> 入库。

对外只暴露 process_file（上传流程）与少量查询封装；列表/详情/删除直接复用 store。
"""
import json
import logging
import os
import uuid

from config import Config
from models import store
from services.documents import extractors
from services.documents.chunker import chunk_text, chunk_text_two_level

logger = logging.getLogger("documents.service")


class DocumentService:
    @staticmethod
    def allowed_ext(filename: str) -> bool:
        ext = os.path.splitext(filename)[1].lower()
        allowed = [e.strip().lower() for e in Config.DOC_ALLOWED_EXT.split(",") if e.strip()]
        return ext in allowed

    @staticmethod
    def max_bytes() -> int:
        return int(Config.DOC_MAX_SIZE_MB * 1024 * 1024)

    @classmethod
    def process_file(cls, src_path: str, original_filename: str, doc_id: str = None) -> dict:
        """处理已保存到本地的上传文件，返回 documents 行（store.create_document 结果）。

        doc_id 可选：由调用方生成（上传路由用它对磁盘文件命名，便于删除时定位）。
        """
        doc_id = doc_id or str(uuid.uuid4().hex)
        file_type = extractors.detect_type(original_filename)
        size = os.path.getsize(src_path)

        def _mk(status, error="", text="", meta=None):
            return store.create_document(
                doc_id, original_filename, file_type, size, status=status,
                error=error, text=text,
                meta_json=json.dumps(meta or {}, ensure_ascii=False),
            )

        if not cls.allowed_ext(original_filename):
            return _mk("error", error=f"不支持的文件类型：{file_type}")

        if size > cls.max_bytes():
            return _mk("error", error=f"文件过大（>{Config.DOC_MAX_SIZE_MB}MB）")

        try:
            text, meta = extractors.extract(src_path, file_type)
        except extractors.ExtractError as e:
            logger.warning("文档抽取失败 %s：%s", original_filename, e)
            return _mk("error", error=str(e))
        except Exception as e:  # 兜底：绝不拖垮上传接口
            logger.exception("文档抽取未知异常 %s", original_filename)
            return _mk("error", error=f"未知错误：{e}")

        if not text.strip():
            # 抽取成功但无文本（如扫描件 PDF），仍记为 done 但无切片
            return _mk("done", text="", meta=meta)

        if Config.DOC_USE_TWO_LEVEL:
            parents, children = chunk_text_two_level(
                text,
                parent_size=Config.DOC_PARENT_CHUNK_SIZE,
                parent_overlap=Config.DOC_PARENT_CHUNK_OVERLAP,
                child_size=Config.DOC_CHILD_CHUNK_SIZE,
                child_overlap=Config.DOC_CHILD_CHUNK_OVERLAP,
            )
            return store.create_document(
                doc_id, original_filename, file_type, size,
                status="done", error="", text=text,
                meta_json=json.dumps(meta, ensure_ascii=False),
                parents=parents, children=children,
            )
        else:
            chunks = chunk_text(text, Config.DOC_CHUNK_SIZE, Config.DOC_CHUNK_OVERLAP)
            return store.create_document(
                doc_id, original_filename, file_type, size,
                status="done", error="", text=text,
                meta_json=json.dumps(meta, ensure_ascii=False),
                chunks=chunks,
            )
