"""运行时配置：可在页面上动态修改并落盘，覆盖启动时的环境变量。

为什么单独做一层：
    config.py 里的 Config 在 import 时就把环境变量读死了，运行时改不了。
    这里维护一份可被接口读写、并持久化到 backend/data/config.json 的运行时配置，
    业务代码（llm_provider）只认这一层，换 key / 换模型无需重启服务。

安全：
    api_key 落盘存明文（仅在本地文件），对外接口一律脱敏，绝不把完整密钥回传给前端。
    前端只拿到「是否已配置」和「尾部掩码」，要改密钥只能由用户重新输入。
"""

import json
import os
import tempfile
import threading
import time
from pathlib import Path

from config import Config

# 配置文件与数据库同目录
CONFIG_PATH = Path(Config.DB_PATH).resolve().parent / "config.json"

# 可重入锁：update() 在 with 块内会调用 _save()/to_public()，二者也加同一把锁，
# 用 RLock 才能支持同一线程嵌套加锁，否则非重入 Lock 会死锁导致进程崩溃。
_LOCK = threading.RLock()

# 允许在前端配置的项；缺省值取自环境变量（首次启动）
_DEFAULTS = {
    "provider": Config.LLM_PROVIDER,
    "base_url": Config.LLM_BASE_URL,
    "api_key": Config.LLM_API_KEY,
    "model": Config.LLM_MODEL,
    "temperature": Config.LLM_TEMPERATURE,
    "rag_mode": Config.RAG_MODE,
    "rag_min_score": 0.12,  # RAG 检索相似度阈值：低于则视为「未命中」
    "rag_min_shared": 2,    # RAG 检索最小共享 token 数：lexical 哈希碰撞可能让乱码低分擦边，
                            # 要求命中分块与 query 至少有 N 个真实共享 token，过滤碰撞型假阳性
}

_runtime = dict(_DEFAULTS)
_loaded = False


def load():
    """启动时调用一次：若磁盘已有配置则覆盖默认。"""
    global _runtime, _loaded
    with _LOCK:
        if CONFIG_PATH.exists():
            try:
                data = json.loads(CONFIG_PATH.read_text("utf-8"))
                _runtime.update({k: data[k] for k in _DEFAULTS if k in data})
            except Exception:
                pass
        _loaded = True
    return dict(_runtime)


def get(key=None):
    with _LOCK:
        if key is None:
            return dict(_runtime)
        return _runtime.get(key)


def to_public():
    """对外返回：api_key 脱敏，并附带是否已配置标记。"""
    with _LOCK:
        cfg = dict(_runtime)
    key = cfg.get("api_key") or ""
    cfg["api_key_set"] = bool(key)
    if key:
        cfg["api_key"] = (key[:6] + "…" + key[-4:]) if len(key) > 10 else "••••"
    else:
        cfg["api_key"] = ""
    return cfg


def update(data: dict):
    """合并更新并落盘。返回脱敏后的配置。"""
    allowed = {"provider", "base_url", "api_key", "model", "temperature", "rag_mode"}
    incoming = {k: v for k, v in data.items() if k in allowed}

    with _LOCK:
        provider = str(incoming.get("provider", _runtime["provider"])).strip().lower()
        if provider not in ("echo", "openai"):
            raise ValueError("模型类型只能是 echo 或 openai")

        base_url = str(incoming.get("base_url", _runtime["base_url"])).strip()
        model = str(incoming.get("model", _runtime["model"])).strip()

        ak = incoming.get("api_key", None)
        if ak is None:
            ak = _runtime["api_key"]          # 前端没传 → 保持原值
        elif isinstance(ak, str) and ak == "__CLEAR__":
            ak = ""                            # 显式清除
        else:
            ak = str(ak).strip()

        try:
            temp = float(incoming.get("temperature", _runtime["temperature"]))
        except (TypeError, ValueError):
            raise ValueError("温度必须是数字")
        if not (0 <= temp <= 2):
            raise ValueError("温度需在 0~2 之间")

        # 回复模式：strict / rag_first
        mode = str(incoming.get("rag_mode", _runtime["rag_mode"])).strip().lower()
        if mode not in ("strict", "rag_first"):
            raise ValueError("回复模式只能是 strict 或 rag_first")

        if provider == "openai" and not ak:
            # 不是致命错误，仅提示；真正调用时 llm_provider 会抛 LLMError
            pass

        _runtime.update({
            "provider": provider,
            "base_url": base_url,
            "api_key": ak,
            "model": model,
            "temperature": temp,
            "rag_mode": mode,
        })
        _save()
        return to_public()


def _save():
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(dict(_runtime), ensure_ascii=False, indent=2)
    last_err = None
    # 先写同目录临时文件，再原子替换：避免写到一半被读端拿到残文件；
    # 并用重试顶过「瞬时锁」（杀软扫描、编辑器自动保存等短暂占用）。
    for attempt in range(4):
        try:
            fd, tmp = tempfile.mkstemp(
                dir=str(CONFIG_PATH.parent), prefix=".config.", suffix=".tmp"
            )
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    f.write(payload)
                os.replace(tmp, str(CONFIG_PATH))
            finally:
                if os.path.exists(tmp):
                    try:
                        os.remove(tmp)
                    except OSError:
                        pass
            return
        except OSError as e:
            last_err = e
            if attempt < 3:
                time.sleep(0.15 * (attempt + 1))
    raise last_err
