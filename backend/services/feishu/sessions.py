"""飞书 群/私聊 → 本地会话 的映射。

私聊：peer_id = 发送者 open_id
群聊：peer_id = chat_id
这样群记忆、私聊记忆互不串，且都能跨会话召回（复用 chat_service 的记忆模块）。
"""

from models import store


def get_or_create_feishu_session(channel: str, peer_id: str) -> str:
    """取 群/私聊 对应的本地会话 id；映射存在但会话已被删（孤儿映射）时自愈重建。"""
    existing = store.get_feishu_session(channel, peer_id)
    if existing and store.get_conversation(existing):
        return existing
    conv = store.create_conversation()
    store.create_feishu_session(channel, peer_id, conv["id"])
    return conv["id"]
