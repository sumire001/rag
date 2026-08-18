"""飞书事件分发：解析 im.message.receive_v1，区分群聊/私聊，走 RAG 回复。

设计要点：
- _do_message 由 lark-oapi 长连接 SDK 调用；它只做「解析 + 抛线程」，不阻塞 SDK 的事件循环。
- _handle 是真正处理逻辑（会话映射 / 调 RAG / 发回），与 SDK 解耦，便于单测。
- 支持「模式」命令切换 RAG 回复模式（strict / rag_first）。
"""

import json
import logging
import threading
from typing import List, Optional

from config import Config
from models import store
from services.feishu import client as feishu_client
from services.feishu.sessions import get_or_create_feishu_session
from services import command_router
from services.rag import service as rag_service

logger = logging.getLogger("feishu")

_client = None


def _get_client() -> feishu_client.FeishuClient:
    global _client
    if _client is None:
        _client = feishu_client.FeishuClient(Config.FEISHU_APP_ID, Config.FEISHU_APP_SECRET)
    return _client


def _do_message(data) -> None:
    """lark-oapi 长连接回调入口；解析后丢到独立线程处理。"""
    try:
        event = data.event
        msg = event.message
        sender = event.sender
        chat_type = msg.chat_type
        msg_type = msg.message_type
        content = json.loads(msg.content or "{}")
        text = content.get("text", "")
        open_id = ""
        if sender and getattr(sender, "sender_id", None):
            open_id = sender.sender_id.open_id or ""
        chat_id = msg.chat_id or ""
        mention_keys = [m.key for m in (msg.mentions or []) if getattr(m, "key", None)]
    except Exception:
        logger.exception("解析飞书事件失败")
        return

    logger.info(
        "收到飞书消息 | chat_type=%s msg_type=%s open_id=%s chat_id=%s text=%r",
        chat_type, msg_type, open_id, chat_id, text[:50],
    )
    threading.Thread(
        target=_handle,
        args=(chat_type, msg_type, text, open_id, chat_id, mention_keys),
        daemon=True,
    ).start()


def _handle(
    chat_type: str,
    msg_type: Optional[str],
    text: str,
    open_id: str,
    chat_id: str,
    mention_keys: List[str],
) -> None:
    try:
        if msg_type != "text":
            _reply(chat_type, open_id, chat_id, "暂不支持该类型消息，当前仅支持文本。")
            return

        # 群聊里去掉 @机器人 占位符（如 @_user_1）
        for key in mention_keys:
            text = text.replace(key, "")
        text = text.strip()

        if not text:
            _reply(chat_type, open_id, chat_id, "你好，我是 AI 助手，有什么可以帮你？")
            return

        # ---- 命令路由：模式切换 / 查询 / 帮助 / 清屏（与 web 端共用）----
        cmd = command_router.route(text)
        if cmd["is_command"]:
            _reply(chat_type, open_id, chat_id, cmd["reply"])
            return

        channel = "group" if chat_type == "group" else "p2p"
        peer_id = chat_id if channel == "group" else open_id
        conv_id = get_or_create_feishu_session(channel, peer_id)

        # 与 web 共用同一张 messages 表：先落用户消息，再落助手消息
        user_msg = store.add_message(conv_id, "user", text)

        # 飞书消息走 RAG：基于「通用IT知识」文档检索 + 生成带引用的回答
        # 传入 conv_id 以带上本会话历史，实现多轮上下文（rag_answer 已自带末尾来源标签）
        result = rag_service.rag_answer(text, conversation_id=conv_id)
        assistant_msg = store.add_message(conv_id, "assistant", result["answer"])

        # 记忆索引：让飞书消息也能被跨会话召回（与 web 一致）
        try:
            from services.memory import retriever as memory_retriever
            memory_retriever.index_message(conv_id, user_msg["id"], "user", text)
            memory_retriever.index_message(conv_id, assistant_msg["id"], "assistant", result["answer"])
        except Exception:
            logger.exception("飞书消息记忆索引失败（不影响回复）")

        _reply(chat_type, open_id, chat_id, result["answer"])
    except Exception:
        logger.exception("处理飞书消息失败")
        try:
            _reply(chat_type, open_id, chat_id, "处理消息时出错了，请稍后再试。")
        except Exception:
            pass


def _reply(chat_type: str, open_id: str, chat_id: str, text: str) -> None:
    _get_client().send_text(chat_type, chat_id, open_id, text)
    logger.info("已回复发往 %s (chat_id=%s, 字数=%d)", chat_type, chat_id, len(text))


def build_dispatcher():
    """构造 lark-oapi 事件分发器，注册消息接收回调。"""
    import lark_oapi as lark

    return (
        lark.EventDispatcherHandler.builder(
            Config.FEISHU_ENCRYPT_KEY, Config.FEISHU_VERIFICATION_TOKEN
        )
        .register_p2_im_message_receive_v1(_do_message)
        .build()
    )
