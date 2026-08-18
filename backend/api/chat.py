"""路由层：参数校验 + 响应封装，业务逻辑一律下沉到 services。

接口一览（统一前缀 /api）：
    GET    /health
    GET    /conversations                  会话列表
    POST   /conversations                  新建会话
    PATCH  /conversations/<cid>            重命名
    DELETE /conversations/<cid>            删除会话
    GET    /conversations/<cid>/messages   会话消息
    DELETE /conversations/<cid>/messages   清空消息
    POST   /chat                           发送消息（一次性返回）
    POST   /chat/stream                    发送消息（SSE 流式返回）
"""

from flask import Blueprint, Response, request, stream_with_context

from config import Config
from models import store
from services import chat_service
from services import runtime_config
from services import command_router
from services.llm_provider import LLMError
from utils.response import fail, ok, sse_event

bp = Blueprint("api", __name__, url_prefix="/api")


def _read_text():
    """从请求体里取出并校验用户输入。"""
    data = request.get_json(silent=True) or {}
    text = (data.get("message") or "").strip()
    cid = data.get("conversation_id") or None
    if not text:
        return None, None, "消息内容不能为空"
    if len(text) > Config.MAX_INPUT_LEN:
        return None, None, f"消息长度不能超过 {Config.MAX_INPUT_LEN} 字"
    return text, cid, None


@bp.get("/health")
def health():
    return ok({
        "status": "up",
        "provider": runtime_config.get("provider"),
        "model": runtime_config.get("model"),
    })


# ---------------- 会话 ----------------

@bp.get("/conversations")
def get_conversations():
    return ok(store.list_conversations())


@bp.post("/conversations")
def post_conversation():
    data = request.get_json(silent=True) or {}
    title = (data.get("title") or "新对话").strip()[:50]
    return ok(store.create_conversation(title))


@bp.patch("/conversations/<cid>")
def patch_conversation(cid):
    data = request.get_json(silent=True) or {}
    title = (data.get("title") or "").strip()[:50]
    if not title:
        return fail("标题不能为空")
    if not store.rename_conversation(cid, title):
        return fail("会话不存在", http_status=404)
    return ok({"id": cid, "title": title})


@bp.delete("/conversations/<cid>")
def remove_conversation(cid):
    if not store.delete_conversation(cid):
        return fail("会话不存在", http_status=404)
    return ok({"id": cid})


# ---------------- 消息 ----------------

@bp.get("/conversations/<cid>/messages")
def get_messages(cid):
    if not store.get_conversation(cid):
        return fail("会话不存在", http_status=404)
    return ok(store.list_messages(cid))


@bp.delete("/conversations/<cid>/messages")
def clear_messages(cid):
    if not store.get_conversation(cid):
        return fail("会话不存在", http_status=404)
    store.clear_messages(cid)
    return ok({"id": cid})


# ---------------- 对话 ----------------

@bp.post("/chat")
def chat():
    text, cid, err = _read_text()
    if err:
        return fail(err)
    # 命令路由优先：命中命令直接返回回执，不走 RAG / 不写消息表
    cmd = command_router.route(text, conversation_id=cid)
    if cmd["is_command"]:
        return ok({"is_command": True, "reply": cmd["reply"], "action": cmd["action"]})
    try:
        conv, msg, title = chat_service.chat_once(cid, text)
    except LLMError as e:
        return fail(str(e), code=502, http_status=502)
    return ok({
        "conversation_id": conv["id"],
        "title": title,
        "message": msg,
    })


@bp.post("/chat/stream")
def chat_stream():
    text, cid, err = _read_text()
    if err:
        return fail(err)

    # 命令路由优先：命中命令时返回一次性 command 事件，不走 RAG
    cmd = command_router.route(text, conversation_id=cid)
    if cmd["is_command"]:
        @stream_with_context
        def gen_command():
            yield sse_event({"type": "command", "reply": cmd["reply"], "action": cmd["action"]})
        return Response(
            gen_command(),
            mimetype="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @stream_with_context
    def generate():
        try:
            for event, payload in chat_service.chat_stream(cid, text):
                yield sse_event({"type": event, **payload})
        except Exception as e:  # 生成器内异常也要以 SSE 形式告知前端
            yield sse_event({"type": "error", "message": f"服务异常: {e}"})

    return Response(
        generate(),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # 关掉 nginx 缓冲，否则流式会被攒包
            # 注意：不要在这里设置 Connection / Transfer-Encoding 等 hop-by-hop 头，
            # 违反 PEP 3333，waitress 会直接 500。分块传输由 WSGI 服务器自动处理。
        },
    )
