"""向量化 provider。

两种来源（由 config.MEMORY_EMBEDDING_PROVIDER 选择）：
    local   = 本地 sentence-transformers，默认 BAAI/bge-small-zh-v1.5，离线、无需 key
    openai  = 任意 OpenAI 兼容的 /embeddings 接口（需 base_url + api_key）
    lexical = 词袋 + 特征哈希，纯本地、零模型、无需联网，语义上只认字面重合

对外只暴露 embed(texts, is_query=False)，返回 (n, dim) 的 float32 数组，
已做 L2 归一化，便于「余弦相似度 = 点积」。

bge 模型要求查询加指令前缀、入库不加，这里用 is_query 区分。

关键设计：本地模型首次使用会从 HuggingFace 下载（数十 MB~上百 MB），可能很慢或
因无网络而失败。为避免它阻塞用户对话，模型在【后台线程】加载：
    - 请求到来时若模型尚未就绪，embed() 抛 ModelNotReady（瞬时），主流程据此跳过记忆；
    - 模型加载成功后，后续请求自动启用记忆召回；
    - 加载失败（无网络/无权限）则标记 disabled（永久），同样不阻塞主对话。
"""

import hashlib
import logging
import os
import re
import struct
import threading
from pathlib import Path

import numpy as np
from config import Config

# 缩短 HuggingFace 下载超时、关掉进度条，避免后台线程长时间空转
os.environ.setdefault("HF_HUB_DOWNLOAD_TIMEOUT", "20")
os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")
os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
# HuggingFace 国内镜像（回退路径走 hf-mirror，避免直连超时）
os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")

logger = logging.getLogger("memory")

# bge 官方推荐的查询前缀（仅用于 query，不用于 passage）
BGE_QUERY_PREFIX = "为这个句子生成表示以用于检索相关文章："

# ---- lexical（词袋 + 特征哈希）向量：无需任何模型，纯本地、离线、确定性 ----
# 用稳定哈希（md5）把 token 映射到固定桶，保证跨进程/重启结果一致。
# 注意：不能用内置 hash()，它受 PYTHONHASHSEED 影响会随进程变化，
# 那样持久化在 SQLite 里的向量在下次启动时会对不上，导致召回失效。
_LEXICAL_DIM = 16384
_TOKEN_RE_EN = re.compile(r"[a-zA-Z0-9]+")        # 英文 / 数字词
_TOKEN_RE_CJK = re.compile(r"[一-鿿]")             # 单个汉字


def _tokenize(text: str):
    """中英文混合分词：英文按词、中文取单字 + 相邻二字 bigram。纯标准库。"""
    text = (text or "").lower()
    toks = list(_TOKEN_RE_EN.findall(text))
    chars = _TOKEN_RE_CJK.findall(text)
    toks.extend(chars)                                   # 单字
    toks.extend("".join(p) for p in zip(chars, chars[1:]))  # 相邻二字 bigram
    return toks


def _stable_bucket(tok: str, dim: int) -> int:
    h = hashlib.md5(tok.encode("utf-8")).digest()
    return struct.unpack("<I", h[:4])[0] % dim


def _embed_lexical(texts, dim=_LEXICAL_DIM):
    """词袋 + 特征哈希：把文本变成固定维度、L2 归一化的稀疏向量。

    不依赖模型，离线可用；语义上只认字面重合（"猫"≠"狗"），但个人聊天记忆足够用。
    与 local/openai 一样返回 (n, dim) float32，可直接喂给 vector_store。
    """
    vecs = []
    for t in texts:
        v = np.zeros(dim, dtype=np.float32)
        for tok in _tokenize(t):
            v[_stable_bucket(tok, dim)] += 1.0
        n = np.linalg.norm(v)
        if n > 0:
            v = v / n
        vecs.append(v)
    return np.stack(vecs)

_LOCAL_MODEL = None
_LOCAL_STATE = "idle"  # idle -> loading -> ready | disabled
_LOCK = threading.Lock()
_LOADER_STARTED = False


class EmbeddingError(Exception):
    """永久不可用（库未装 / 模型加载彻底失败 / 没配 key 等）。"""


class ModelNotReady(Exception):
    """瞬时：本地模型还在后台加载中，本次跳过记忆即可。"""


def _resolve_local_model_path() -> str:
    """确定 local embedding 模型的加载源，优先级从高到低：

    1) Config.MEMORY_EMBEDDING_MODEL_DIR（用户显式指定的本地模型目录）
    2) backend/data/models 下已缓存的模型（之前 ModelScope 下载过）
    3) ModelScope（魔搭）在线下载到 backend/data/models（国内可达，无需翻墙）
    4) 回退 HuggingFace（sentence-transformers 默认行为，已设 HF_ENDPOINT 镜像）

    返回本地目录路径或模型名（让 SentenceTransformer 自行处理）。
    """
    explicit = (Config.MEMORY_EMBEDDING_MODEL_DIR or "").strip()
    if explicit:
        if os.path.isdir(explicit):
            return explicit
        logger.warning("MEMORY_EMBEDDING_MODEL_DIR 不存在，忽略：%s", explicit)

    model_name = Config.MEMORY_EMBEDDING_MODEL
    cache_dir = str(Path(Config.DB_PATH).resolve().parent / "models")
    cache_root = Path(cache_dir)

    # 已缓存：新版 modelscope 布局 cache_dir/models/<org>--<name>/snapshots/<rev>/
    org, _, name = model_name.partition("/")
    if org and name:
        snapshots = cache_root / "models" / f"{org}--{name}" / "snapshots"
        if snapshots.is_dir():
            for rev in snapshots.iterdir():
                if (rev / "config.json").is_file():
                    return str(rev)
    # 旧版布局 cache_dir/<org>/<name>/
    legacy = cache_root / model_name
    if legacy.is_dir() and (legacy / "config.json").is_file():
        return str(legacy)

    # ModelScope（魔搭）：模型 id 与 HuggingFace 一致
    try:
        from modelscope import snapshot_download

        local = snapshot_download(model_name, cache_dir=cache_dir)
        logger.info("已从 ModelScope 下载模型：%s -> %s", model_name, local)
        return local
    except Exception as e:
        logger.warning("ModelScope 下载失败，回退 HuggingFace：%s", e)

    return model_name


def _background_load():
    global _LOCAL_MODEL, _LOCAL_STATE
    try:
        from sentence_transformers import SentenceTransformer

        model = SentenceTransformer(_resolve_local_model_path())
        with _LOCK:
            _LOCAL_MODEL = model
            _LOCAL_STATE = "ready"
        logger.info("本地 embedding 模型加载完成：%s", Config.MEMORY_EMBEDDING_MODEL)
    except Exception as e:
        with _LOCK:
            _LOCAL_STATE = "disabled"
        logger.warning("本地 embedding 模型加载失败，记忆层已停用：%s", e)


def _ensure_loader_started():
    global _LOADER_STARTED, _LOCAL_STATE
    with _LOCK:
        if _LOADER_STARTED:
            return
        _LOADER_STARTED = True
        if _LOCAL_STATE == "idle":
            _LOCAL_STATE = "loading"
    t = threading.Thread(target=_background_load, daemon=True)
    t.start()


def _embed_local(texts, is_query):
    _ensure_loader_started()
    with _LOCK:
        state = _LOCAL_STATE
        model = _LOCAL_MODEL
    if state == "disabled":
        raise EmbeddingError("本地 embedding 模型不可用（加载失败）")
    if state != "ready":
        raise ModelNotReady("本地 embedding 模型加载中")
    if is_query:
        texts = [BGE_QUERY_PREFIX + t for t in texts]
    vecs = model.encode(
        texts,
        normalize_embeddings=True,
        convert_to_numpy=True,
        show_progress_bar=False,
    )
    return np.asarray(vecs, dtype=np.float32)


def _embed_openai(texts):
    import requests

    url = Config.MEMORY_EMBEDDING_BASE_URL.rstrip("/") + "/embeddings"
    headers = {
        "Authorization": f"Bearer {Config.MEMORY_EMBEDDING_API_KEY}",
        "Content-Type": "application/json",
    }
    out = []
    for t in texts:
        r = requests.post(
            url,
            headers=headers,
            json={"model": Config.MEMORY_EMBEDDING_MODEL, "input": t},
            timeout=Config.LLM_TIMEOUT,
        )
        if r.status_code != 200:
            raise EmbeddingError(f"embedding 接口返回 {r.status_code}: {r.text[:200]}")
        out.append(r.json()["data"][0]["embedding"])
    return np.asarray(out, dtype=np.float32)


def embed(texts, is_query=False):
    """返回 (n, dim) float32 数组；空输入返回 (0,1)。

    provider 由 config.MEMORY_EMBEDDING_PROVIDER 决定：
        local   -> 本地 bge 模型（后台线程懒加载）
        openai  -> 远程 /embeddings 接口
        lexical -> 词袋 + 特征哈希（默认 fallback 之外的新增分支）
    """
    if not texts:
        return np.zeros((0, 1), dtype=np.float32)
    provider = (Config.MEMORY_EMBEDDING_PROVIDER or "local").lower()
    if provider == "openai":
        return _embed_openai(texts)
    if provider == "lexical":
        return _embed_lexical(texts)
    return _embed_local(texts, is_query)
