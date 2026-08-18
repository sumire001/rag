"""文档处理 API。

接口一览（统一前缀 /api）：
    POST   /documents/upload       上传并解析文档（multipart: file）
    GET    /documents              文档列表
    GET    /documents/<id>         文档详情（含抽取全文）
    GET    /documents/<id>/chunks  文档切片列表
    DELETE /documents/<id>         删除文档（含切片与磁盘文件）
"""
import logging
import os
import uuid

from flask import Blueprint, request

from config import Config
from models import store
from services.documents import service as doc_service
from utils.response import fail, ok

logger = logging.getLogger("api.documents")

bp = Blueprint("documents", __name__, url_prefix="/api/documents")


def _ensure_upload_dir():
    os.makedirs(Config.DOC_UPLOAD_DIR, exist_ok=True)


@bp.post("/upload")
def upload():
    if "file" not in request.files:
        return fail("缺少上传文件（字段名应为 file）")
    f = request.files["file"]
    original = f.filename or ""
    if not original:
        return fail("文件名为空")

    svc = doc_service.DocumentService
    if not svc.allowed_ext(original):
        return fail(f"不支持的文件类型，允许：{Config.DOC_ALLOWED_EXT}")

    # 先落地到上传目录，文件名以文档 id 命名，便于删除时定位
    _ensure_upload_dir()
    doc_id = uuid.uuid4().hex
    ext = os.path.splitext(original)[1]
    saved_name = f"{doc_id}{ext}"
    saved_path = os.path.join(Config.DOC_UPLOAD_DIR, saved_name)
    try:
        f.save(saved_path)
    except Exception as e:
        return fail(f"文件保存失败：{e}")

    try:
        result = svc.process_file(saved_path, original, doc_id=doc_id)
    except Exception as e:
        if os.path.exists(saved_path):
            os.remove(saved_path)
        return fail(f"文档处理异常：{e}")

    # 处理成功后保留磁盘文件（在 DOC_UPLOAD_DIR），供后续下载/重解析；删除文档时一并清理
    return ok({
        "id": result["id"],
        "filename": result["filename"],
        "file_type": result["file_type"],
        "size": result["size"],
        "status": result["status"],
        "error": result["error"],
        "chunk_count": result["chunk_count"],
    })


@bp.get("")
@bp.get("/")
def list_docs():
    return ok(store.list_documents())


@bp.get("/<doc_id>")
def get_doc(doc_id: str):
    doc = store.get_document(doc_id)
    if not doc:
        return fail("文档不存在", code=404, http_status=404)
    return ok(doc)


@bp.get("/<doc_id>/chunks")
def get_chunks(doc_id: str):
    doc = store.get_document(doc_id)
    if not doc:
        return fail("文档不存在", code=404, http_status=404)
    return ok(store.get_document_chunks(doc_id))


@bp.delete("/<doc_id>")
def delete_doc(doc_id: str):
    doc = store.get_document(doc_id)
    if not doc:
        return fail("文档不存在", code=404, http_status=404)
    # 清理磁盘文件：文件名 = f"{doc_id}{原扩展名}"
    try:
        ext = os.path.splitext(doc.get("filename") or "")[1]
        candidate = os.path.join(Config.DOC_UPLOAD_DIR, f"{doc_id}{ext}")
        if ext and os.path.exists(candidate):
            os.remove(candidate)
    except OSError as e:
        logger.warning("删除文档磁盘文件失败 %s：%s", doc_id, e)
    ok_del = store.delete_document(doc_id)
    return ok({"deleted": ok_del})
