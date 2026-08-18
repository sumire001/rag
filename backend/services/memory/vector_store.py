"""向量存储：复用 SQLite（embeddings 表），本地用 numpy 算余弦相似度。

不依赖任何向量数据库。数据量小时全量线性扫描足够快；量大再换 FAISS/Chroma，
接口不变（add / search）。

向量以 float32 的 BLOB 存盘（紧凑、读取即 numpy）。写入时已归一化，
因此余弦相似度等价于点积。
"""

import numpy as np

from models import store


def _to_blob(vec) -> bytes:
    return np.ascontiguousarray(vec, dtype=np.float32).tobytes()


def _from_blob(blob) -> np.ndarray:
    return np.frombuffer(blob, dtype=np.float32)


def add(message_id: int, conversation_id: str, role: str, content: str, vector) -> None:
    store.add_embedding(message_id, conversation_id, role, content, _to_blob(vector))


def search(query_vec, top_k: int = 5, exclude_conv_id: str = None, min_score: float = 0.0) -> list:
    """返回 top_k 条最相似的历史片段。query_vec 为 1 维 float32 数组。"""
    rows = store.list_embeddings(exclude_conv_id)
    if not rows:
        return []

    q = np.asarray(query_vec, dtype=np.float32)
    q = q / (np.linalg.norm(q) + 1e-9)
    qdim = q.shape[0]

    # 维度过滤：切换 embedding provider（如 bge 512 维 → lexical 16384 维）后，
    # 老向量维度与新向量不一致，直接 stack 会崩。只比对同维度向量，维度不符的跳过。
    vecs, kept = [], []
    for r in rows:
        v = _from_blob(r["vector"])
        if v.shape[0] != qdim:
            continue
        vecs.append(v)
        kept.append(r)
    if not vecs:
        return []

    matrix = np.stack(vecs)
    sims = matrix @ q  # 已归一化 → 点积即余弦

    top_idx = np.argsort(-sims)[:top_k]
    out = []
    for i in top_idx:
        score = float(sims[i])
        if min_score and score < min_score:
            continue
        r = kept[int(i)]
        out.append({
            "message_id": r["message_id"],
            "conversation_id": r["conversation_id"],
            "role": r["role"],
            "content": r["content"],
            "score": round(score, 4),
        })
    return out
