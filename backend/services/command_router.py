"""命令路由：把用户输入解析为「命令」或「普通消息」。

web 端与飞书端共用本模块，保证命令语义一致：
  /mode strict        → 仅按《通用IT知识》回答（资料没有就拒绝）
  /mode rag_first     → 优先用资料，资料没有时回落模型通用知识（默认）
  /mode               → 查询当前回复模式
  /help               → 显示命令帮助
  /clear              → 清空当前会话（需要 conversation_id）
中文等价：模式 严格 / 模式 优先 / 模式 / 帮助 / 清除

route(text, conversation_id=None) -> dict:
  {is_command: bool, action, reply, clear}
  action ∈ {set_mode, query_mode, help, clear, mode_unknown, None}
"""
import re

from models import store
from services.rag import service as rag_service

HELP_TEXT = (
    "🛠 可用命令：\n"
    "· /mode strict    仅按《通用IT知识》回答，资料没有就拒绝\n"
    "· /mode rag_first 优先用资料，资料没有时用模型通用知识（默认）\n"
    "· /mode           查看当前回复模式\n"
    "· /clear          清空当前会话的消息\n"
    "· /help           显示本帮助\n"
    "（也支持中文：模式 严格 / 模式 优先 / 模式 / 帮助 / 清除）"
)


def route(text, conversation_id=None):
    """返回命令解析结果。is_command=False 表示这是一条普通消息，可继续走 RAG。"""
    t = (text or "").strip()
    if not t:
        return {"is_command": False}

    low = t.lower()

    # 帮助
    if low in ("/help", "帮助", "?", "？", "命令", "命令帮助"):
        return {"is_command": True, "action": "help", "reply": HELP_TEXT}

    # 清空当前会话
    if low in ("/clear", "清除", "清空", "清空会话", "清屏"):
        if conversation_id:
            store.clear_messages(conversation_id)
            return {"is_command": True, "action": "clear",
                    "reply": "已清空当前会话的消息。"}
        return {"is_command": True, "action": "clear",
                "reply": "当前没有进行中的会话，无需清空。"}

    # 模式切换 / 查询：仅匹配以「/mode」或「模式 」开头，避免误伤如「模型的…」
    target_mode = None
    query_mode = False
    if re.match(r"^/mode(\s|$)", low) or re.match(r"^模式(\s|$)", low):
        tail = re.sub(r"^(/mode|模式)\s*", "", low).strip()
        if tail in ("strict", "严格"):
            target_mode = "strict"
        elif tail in ("rag_first", "优先", "rag first", "通用", "general"):
            target_mode = "rag_first"
        elif tail in ("", "查询", "当前", "当前模式", "now", "query"):
            query_mode = True
        else:
            return {"is_command": True, "action": "mode_unknown",
                    "reply": "未知模式，仅支持 strict（严格）或 rag_first（优先）。"}
    elif low == "/strict":
        target_mode = "strict"
    elif low in ("/rag_first", "/ragfirst"):
        target_mode = "rag_first"

    if query_mode:
        cur = rag_service.get_rag_mode()
        return {"is_command": True, "action": "query_mode",
                "reply": "当前回复模式：{desc}（{mode}）".format(
                    desc=rag_service.mode_description(cur), mode=cur)}

    if target_mode:
        rag_service.set_rag_mode(target_mode)
        desc = rag_service.mode_description(target_mode)
        return {"is_command": True, "action": "set_mode",
                "reply": "已切换到「{desc}」（{mode}）。\n\n{desc}".format(
                    desc=desc, mode=target_mode)}

    return {"is_command": False}
