"""基于 lexical 向量的文档检索（纯本地、无需模型）。

复用记忆模块同款「词袋 + 特征哈希」思路（md5 稳定哈希，跨进程一致），
对 document_chunks 表建立内存索引，按余弦相似度返回 top-K 相关分块，
附带来源元数据（文件名、分块序号、章节标题）。
"""
import hashlib
import logging
import re
import struct

import numpy as np

from models import store

logger = logging.getLogger("rag.retriever")

_DIM = 16384
_TOKEN_RE_EN = re.compile(r"[a-zA-Z0-9]+")          # 英文 / 数字词
_TOKEN_RE_CJK = re.compile(r"[一-鿿]")              # 单个汉字


def _tokenize(text: str):
    """中英文混合分词：英文按词、中文取单字 + 相邻二字 bigram。纯标准库。"""
    text = (text or "").lower()
    toks = list(_TOKEN_RE_EN.findall(text))
    chars = _TOKEN_RE_CJK.findall(text)
    toks.extend(chars)                                       # 单字
    toks.extend("".join(p) for p in zip(chars, chars[1:]))    # 相邻二字 bigram
    return toks


def _bucket(tok: str, dim: int) -> int:
    h = hashlib.md5(tok.encode("utf-8")).digest()
    return struct.unpack("<I", h[:4])[0] % dim


def _embed(text: str) -> np.ndarray:
    v = np.zeros(_DIM, dtype=np.float32)
    for tok in _tokenize(text):
        v[_bucket(tok, _DIM)] += 1.0
    n = np.linalg.norm(v)
    if n > 0:
        v = v / n
    return v


class DocumentRetriever:
    def __init__(self):
        self._chunks = []          # list[{"doc_id","idx","content","filename","granularity","parent_idx"}]
        self._vecs = np.zeros((0, _DIM), dtype=np.float32)
        self._built = False

    def build(self) -> None:
        # (doc_id, idx, content, filename, granularity, parent_idx)
        rows = store.all_document_chunks()
        self._chunks = [
            {
                "doc_id": r[0],
                "idx": r[1],
                "content": r[2],
                "filename": r[3],
                "granularity": r[4],
                "parent_idx": r[5],
            }
            for r in rows
        ]
        if self._chunks:
            self._vecs = np.stack([_embed(c["content"]) for c in self._chunks])
        else:
            self._vecs = np.zeros((0, _DIM), dtype=np.float32)
        self._built = True
        logger.info("RAG 索引构建完成，共 %d 个分块（child/parent 全部索引）", len(self._chunks))

    def search(self, query: str, top_k: int = 4, min_score: float = None,
                min_shared: int = None) -> list:
        if not self._built:
            self.build()
        if len(self._chunks) == 0:
            return []
        # 相似度阈值：低于该值的分块视为「无关」，不计入命中。
        # lexical 单字余弦绝对值普遍偏低，默认 0.12 经实测可在真相关与噪音间取得平衡
        # （真相关问题约 0.12~0.37，噪音/乱码约 0.02~0.10）。
        if min_score is None:
            try:
                from services import runtime_config
                min_score = float(runtime_config.get("rag_min_score") or 0.12)
            except Exception:
                min_score = 0.12
        # 最小共享 token 数：pure-lexical 哈希（16384 桶）存在随机碰撞，
        # 长乱码偶尔能凭碰撞把余弦顶过阈值（如 "zxcvbnm qwertyuiop asdfghjkl" 实测 0.13）。
        # 真相关 query 会与资料共享多个 token（6+），碰撞假阳性通常只共享 1 个，
        # 故要求命中分块至少与 query 有 N 个真实共享 token，从根上挡掉碰撞型假命中。
        if min_shared is None:
            try:
                from services import runtime_config
                min_shared = int(runtime_config.get("rag_min_shared") or 2)
            except Exception:
                min_shared = 2
        qv = _embed(query)
        q_nonzero = set(int(x) for x in np.where(qv != 0)[0].tolist())
        sims = self._vecs @ qv
        results = []
        # 已按相似度降序，低于阈值的后面不可能再达标，可直接 break
        for i in np.argsort(-sims):
            s = float(sims[i])
            if s < min_score:
                break
            cvec = self._vecs[i]
            c_nonzero = set(int(x) for x in np.where(cvec != 0)[0].tolist())
            if len(q_nonzero & c_nonzero) < min_shared:
                continue
            c = self._chunks[i]
            results.append({
                "doc_id": c["doc_id"],
                "idx": c["idx"],
                "content": c["content"],
                "filename": c["filename"],
                "granularity": c["granularity"],
                "parent_idx": c["parent_idx"],
                "score": s,
            })
            if len(results) >= top_k:
                break
        return results


# 模块级单例：后端启动时 build 一次即可（文档更新后调用 rebuild()）
_retriever = DocumentRetriever()


def rebuild() -> None:
    _retriever.build()


def search(query: str, top_k: int = 4) -> list:
    return _retriever.search(query, top_k=top_k)
