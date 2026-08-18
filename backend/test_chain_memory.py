"""记忆模块端到端链条测试（live，打真实后端）。

测试链路：发消息 -> 落库 -> 写 embedding(lexical) -> 跨会话召回 -> 层1摘要触发。
运行： backend/.venv/Scripts/python.exe test_chain_memory.py
前置：后端已在跑（默认 http://127.0.0.1:5000），且 .env 的 MEMORY_EMBEDDING_PROVIDER=lexical。
"""

import os
import sys
import json
import sqlite3
import urllib.request
from dotenv import load_dotenv

load_dotenv()  # 必须在 import config 之前，和 app.py 保持一致，否则读不到 .env 的 lexical

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import Config
from models import store
from services.memory import retriever

BASE = "http://127.0.0.1:5000"
HDR = {"Content-Type": "application/json"}


def db_path():
    return Config.DB_PATH


def embeddings_count():
    conn = sqlite3.connect(db_path())
    n = conn.execute("SELECT COUNT(*) FROM embeddings").fetchone()[0]
    conn.close()
    return n


def post_chat(message, conversation_id=None, timeout=90):
    payload = {"message": message}
    if conversation_id:
        payload["conversation_id"] = conversation_id
    req = urllib.request.Request(
        BASE + "/api/chat",
        data=json.dumps(payload).encode("utf-8"),
        headers=HDR,
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        body = json.loads(resp.read().decode("utf-8"))
    if body.get("code") != 0:
        raise RuntimeError("API 返回错误: %s" % body)
    return body["data"]


def main():
    print("=" * 60)
    print("记忆链条测试  (provider=%s, dim 应为 16384)" % Config.MEMORY_EMBEDDING_PROVIDER)
    print("=" * 60)

    # ---- 阶段1：在会话A种入明确事实 ----
    print("\n[1] 会话A：种入主题事实")
    r1 = post_chat("我的主力后端框架是 FastAPI，因为我喜欢它轻量、支持异步。")
    conv_a = r1["conversation_id"]
    print("    convA =", conv_a)
    print("    回复  =", r1["message"]["content"][:60].replace("\n", " "), "...")

    r2 = post_chat("另外我前端只用原生 HTML/CSS/JS，不引任何框架。", conversation_id=conv_a)
    print("    回复2 =", r2["message"]["content"][:60].replace("\n", " "), "...")

    # ---- 阶段2：新会话B，问一个能从A召回的问题 ----
    print("\n[2] 新会话B：问一个依赖A上下文的问题")
    query = "我之前跟你说过，我主力后端框架是哪个来着？"
    r3 = post_chat(query)
    conv_b = r3["conversation_id"]
    print("    convB =", conv_b)
    print("    回复  =", r3["message"]["content"][:120].replace("\n", " "), "...")

    # ---- 阶段3：直接验证层2跨会话召回（确定性证据）----
    print("\n[3] 层2 跨会话召回检索（对B的query在真实库上跑 recall）")
    recalled = retriever.recall(conv_b, query)
    if not recalled:
        print("    !! 未召回任何片段 —— 记忆链路异常")
        return 1
    for x in recalled:
        print("    conv=%s role=%-9s score=%.4f :: %s" % (
            x["conversation_id"][:8], x["role"], x["score"],
            x["content"][:48].replace("\n", " ")))

    hit_a = any(x["conversation_id"] == conv_a for x in recalled)
    print("    命中会话A:", "YES (OK)" if hit_a else "NO (FAIL)")

    # ---- 阶段4：持久化 / 维度检查 ----
    print("\n[4] 持久化与维度检查")
    conn = sqlite3.connect(db_path())
    rows = conn.execute(
        "SELECT role, length(vector) FROM embeddings "
        "WHERE conversation_id=? ORDER BY message_id", (conv_a,)
    ).fetchall()
    conn.close()
    print("    会话A 已写 embedding 条数:", len(rows))
    dim_ok = True
    for role, blen in rows:
        dim = blen // 4
        ok = (dim == 16384)
        dim_ok = dim_ok and ok
        print("      role=%-9s 维度=%d %s" % (role, dim, "OK" if ok else "FAIL(应为16384)"))

    # ---- 阶段5：层1 摘要触发（构造>20条后调 _ensure_summary）----
    print("\n[5] 层1 会话内摘要触发检查（构造21条后调 _ensure_summary）")
    from services import chat_service
    probe = store.create_conversation()["id"]
    for i in range(21):
        store.add_message(probe, "user", "测试第%d句：我喜欢用 FastAPI 做后端。" % i)
        store.add_message(probe, "assistant", "收到，第%d句已记录。" % i)
    summary = chat_service._ensure_summary(probe)
    print("    摘要长度:", len(summary), "字")
    if summary:
        print("    摘要预览:", summary[:120].replace("\n", " ") + "...")
    print("    层1 生效:", "YES (OK)" if summary else "NO (FAIL)")

    try:
        store.delete_conversation(probe)
    except Exception:
        pass

    print("\n" + "=" * 60)
    all_ok = hit_a and len(rows) >= 2 and dim_ok and bool(summary)
    print("链条测试结果:", "ALL PASS (OK)" if all_ok else "部分异常 (FAIL)")
    print("=" * 60)
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
