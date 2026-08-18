"""记忆检索高层封装：写入索引 + 跨会话召回。

设计原则：记忆是「增强」，不是「必需」。
    - embedding 不可用（没装库 / 模型下载失败 / 没配 key）时，整体优雅降级，
      不抛错、不拖慢主对话流程。
    - 探测结果缓存，避免每条消息都重试。
"""

import logging

import numpy as np
from config import Config

from services.memory import embeddings, vector_store

logger = logging.getLogger("memory")

_MEMORY_AVAILABLE = None  # None=未探测, True/False


def _probe_available() -> bool:
    global _MEMORY_AVAILABLE
    if _MEMORY_AVAILABLE is not None:
        return _MEMORY_AVAILABLE
    if not Config.MEMORY_ENABLED:
        _MEMORY_AVAILABLE = False
        return False
    try:
        provider = (Config.MEMORY_EMBEDDING_PROVIDER or "local").lower()
        if provider == "openai":
            ok = bool(Config.MEMORY_EMBEDDING_API_KEY)
        elif provider == "lexical":
            ok = True  # 纯本地词袋，无需模型 / key
        else:  # local
            import importlib
            importlib.import_module("sentence_transformers")
            ok = True
    except Exception as e:
        logger.warning("记忆功能不可用，已停用：%s", e)
        ok = False
    _MEMORY_AVAILABLE = ok
    return ok


def _safe_embed(texts, is_query=False):
    """embedding 失败则标记不可用并返回 None，主流程据此跳过记忆。"""
    global _MEMORY_AVAILABLE
    if not _probe_available():
        return None
    try:
        return embeddings.embed(texts, is_query=is_query)
    except embeddings.EmbeddingError as e:
        # 永久不可用（库缺失 / 模型加载失败 / 没配 key）：停用记忆层
        _MEMORY_AVAILABLE = False
        logger.warning("embedding 永久不可用，记忆召回已停用：%s", e)
        return None
    except embeddings.ModelNotReady:
        # 瞬时：本地模型仍在后台加载，本次跳过记忆即可，待下次请求再试
        return None
    except Exception as e:
        # 其它意外错误按瞬时处理，避免单次抖动就永久关掉记忆
        logger.warning("embedding 调用失败（本次跳过）：%s", e)
        return None


def index_message(conversation_id: str, message_id: int, role: str, content: str) -> None:
    """把一条消息写入向量索引（仅 user/assistant）。失败静默忽略。"""
    if role not in ("user", "assistant"):
        return
    if not content or not content.strip():
        return
    vecs = _safe_embed([content])
    if vecs is None:
        return
    try:
        vector_store.add(message_id, conversation_id, role, content, vecs[0])
    except Exception as e:
        logger.warning("写入向量索引失败（已忽略）：%s", e)


def recall(conversation_id: str, query: str, top_k: int = None) -> list:
    """跨会话召回与 query 相关的历史片段。无结果/不可用时返回 []。"""
    if not _probe_available() or not query or not query.strip():
        return []
    top_k = top_k or Config.MEMORY_TOP_K
    qvec = _safe_embed([query], is_query=True)
    if qvec is None:
        return []
    try:
        exclude = conversation_id if Config.MEMORY_CROSS_CONV else None
        return vector_store.search(
            qvec[0],
            top_k=top_k,
            exclude_conv_id=exclude,
            min_score=Config.MEMORY_MIN_SCORE,
        )
    except Exception as e:
        logger.warning("向量召回失败（已忽略）：%s", e)
        return []


def format_recall(hits: list) -> str:
    """把召回结果拼成注入 system 上下文的文本块。"""
    if not hits:
        return ""
    lines = []
    for h in hits:
        label = "用户" if h["role"] == "user" else "助手"
        lines.append(f"- （{label}）{h['content']}")
    return (
        "以下是与用户当前问题相关的历史对话片段（可能来自过往会话），"
        "仅在相关时参考：\n" + "\n".join(lines)
    )
