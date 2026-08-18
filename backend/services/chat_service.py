"""业务编排层：会话/消息的读写 + 拼上下文 + 调模型。

路由层只做参数校验和响应封装，真正的流程都在这里。
"""

import logging
from typing import Iterator, List, Tuple

from config import Config
from models import store
from services.llm_provider import LLMError, get_provider
from services.rag import service as rag_service

logger = logging.getLogger("chat")


def ensure_conversation(conversation_id: str = None) -> dict:
    """有 id 就取，取不到或没传就新建。"""
    if conversation_id:
        conv = store.get_conversation(conversation_id)
        if conv:
            return conv
    return store.create_conversation()


def build_context(conversation_id: str, user_text: str = None) -> List[dict]:
    """组装发给模型的上下文：

    1) system prompt
    2) 层1 会话内摘要（超窗口的早期消息压缩）
    3) 层2 跨会话召回（与当前问题相关的历史片段）
    4) 最近 N 条原文历史
    """
    history = store.recent_messages(conversation_id, Config.HISTORY_LIMIT)
    messages = [{"role": "system", "content": Config.SYSTEM_PROMPT}]

    # 层1：会话内早期消息摘要
    summary = _ensure_summary(conversation_id)
    if summary:
        messages.append({
            "role": "system",
            "content": "以下是本对话早期内容的摘要，请结合它理解当前问题：\n" + summary,
        })

    # 层2：跨会话召回
    if user_text:
        from services.memory import retriever
        block = retriever.format_recall(retriever.recall(conversation_id, user_text))
        if block:
            messages.append({"role": "system", "content": block})

    messages.extend({"role": m["role"], "content": m["content"]} for m in history)
    return messages


def _ensure_summary(conversation_id: str) -> str:
    """超窗口时缓存一份早期消息摘要，返回摘要文本（未超窗返回 ''）。"""
    conv = store.get_conversation(conversation_id)
    if not conv:
        return ""
    msgs = store.list_messages(conversation_id)
    if len(msgs) <= Config.HISTORY_LIMIT:
        return ""
    old = msgs[:-Config.HISTORY_LIMIT]
    if conv.get("summary_count", 0) >= len(old):
        return conv.get("summary", "") or ""
    # 重新摘要全部 old（old 每次只多 1 条，代价可接受）
    text = "\n".join(
        f"{'用户' if m['role'] == 'user' else '助手'}：{m['content']}" for m in old
    )
    try:
        summary = _summarize(text)
    except Exception:
        summary = conv.get("summary", "") or ""  # 摘要失败则沿用旧摘要
    store.update_conversation_summary(conversation_id, summary, len(old))
    return summary


def _summarize(text: str) -> str:
    """用当前模型把一段对话压缩成可复用的要点摘要。"""
    prompt = (
        "请用简洁的中文总结以下对话的关键信息、用户偏好与未完成任务，"
        "不超过 300 字，保留可被后续对话复用的要点：\n\n" + text
    )
    return get_provider().complete([{"role": "user", "content": prompt}])


def auto_title(conversation_id: str, text: str) -> str:
    """首条用户消息自动作为会话标题。"""
    conv = store.get_conversation(conversation_id)
    if not conv or conv["title"] != "新对话":
        return conv["title"] if conv else ""
    title = text.strip().replace("\n", " ")[:20] or "新对话"
    store.rename_conversation(conversation_id, title)
    return title


def chat_once(conversation_id: str, text: str) -> Tuple[dict, dict, str]:
    """非流式：返回 (会话, 助手消息, 标题)。

    走 RAG：基于《通用IT知识》检索 + 按当前回复模式（strict / rag_first）生成，
    与飞书端共用 rag_service，两边行为一致。
    """
    conv = ensure_conversation(conversation_id)
    cid = conv["id"]

    user_msg = store.add_message(cid, "user", text)
    title = auto_title(cid, text)

    result = rag_service.rag_answer(text, conversation_id=cid)

    assistant_msg = store.add_message(cid, "assistant", result["answer"])

    _index_memory(cid, user_msg["id"], "user", text)
    _index_memory(cid, assistant_msg["id"], "assistant", result["answer"])

    return conv, assistant_msg, title


def _index_memory(conversation_id: str, message_id, role: str, content: str) -> None:
    """记忆索引：让消息可被跨会话召回（失败不影响主流程）。"""
    try:
        from services.memory import retriever as memory_retriever
        memory_retriever.index_message(conversation_id, message_id, role, content)
    except Exception:
        logger.exception("记忆索引失败（不影响回复）")


def chat_stream(conversation_id: str, text: str):
    """流式（伪流式）：先一次性生成 RAG 答案，再分片推送做打字机效果。

    事件类型：
        start  -> {conversation_id, title}
        delta  -> {content}
        done   -> {message_id, content}
        error  -> {message}
    """
    conv = ensure_conversation(conversation_id)
    cid = conv["id"]

    user_msg = store.add_message(cid, "user", text)
    title = auto_title(cid, text)

    yield "start", {"conversation_id": cid, "title": title}

    try:
        result = rag_service.rag_answer(text, conversation_id=cid)
    except Exception as e:
        yield "error", {"message": f"RAG 调用异常: {e}"}
        return

    answer = result["answer"]
    # 后端已一次性生成，这里按片段推送，前端呈现打字机效果
    step = 8
    for i in range(0, len(answer), step):
        yield "delta", {"content": answer[i:i + step]}

    if answer:
        saved = store.add_message(cid, "assistant", answer)
        _index_memory(cid, user_msg["id"], "user", text)
        _index_memory(cid, saved["id"], "assistant", answer)
        yield "done", {"message_id": saved["id"], "content": answer}
    else:
        yield "error", {"message": "模型未返回任何内容"}
