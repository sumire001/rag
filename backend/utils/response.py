"""统一响应格式，前端只需判断 code 是否为 0。"""

import json

from flask import jsonify


def ok(data=None):
    return jsonify({"code": 0, "msg": "ok", "data": data})


def fail(msg: str, code: int = 400, http_status: int = 400):
    return jsonify({"code": code, "msg": msg, "data": None}), http_status


def sse_event(payload: dict) -> str:
    """把一个 dict 打包成一条 SSE 消息。"""
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
