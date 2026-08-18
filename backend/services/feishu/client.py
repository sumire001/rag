"""飞书开放平台客户端：tenant_access_token 获取 + 发消息（含长文本分片）。

只用 requests，不依赖 lark-oapi 的请求构建，避免 SDK 版本差异带来的接口变动。
"""

import json
import time

import requests
from config import Config

FEISHU_DOMAIN = "https://open.feishu.cn"


class FeishuClient:
    def __init__(self, app_id: str, app_secret: str, domain: str = FEISHU_DOMAIN):
        self.app_id = app_id
        self.app_secret = app_secret
        self.domain = domain
        self._token: str = ""
        self._expire_at: float = 0.0

    def _ensure_token(self) -> str:
        if self._token and time.time() < self._expire_at - 60:
            return self._token
        resp = requests.post(
            f"{self.domain}/open-apis/auth/v3/tenant_access_token/internal",
            json={"app_id": self.app_id, "app_secret": self.app_secret},
            timeout=10,
        )
        data = resp.json()
        if data.get("code") != 0:
            raise RuntimeError(f"获取 tenant_access_token 失败: {data}")
        self._token = data["tenant_access_token"]
        self._expire_at = time.time() + data.get("expire", 7200)
        return self._token

    def send_text(self, chat_type: str, chat_id: str, open_id: str, text: str) -> None:
        """把文本回传给对应的群或私聊。超长自动分多条。"""
        token = self._ensure_token()
        if chat_type == "group":
            receive_id_type, receive_id = "chat_id", chat_id
        else:
            receive_id_type, receive_id = "open_id", open_id

        for piece in _chunk(text, Config.FEISHU_REPLY_CHUNK):
            body = {
                "receive_id": receive_id,
                "msg_type": "text",
                "content": json.dumps({"text": piece}, ensure_ascii=False),
            }
            resp = requests.post(
                f"{self.domain}/open-apis/im/v1/messages?receive_id_type={receive_id_type}",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json; charset=utf-8",
                },
                data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
                timeout=15,
            )
            data = resp.json()
            if data.get("code") != 0:
                raise RuntimeError(f"发送飞书消息失败: {data}")


def _chunk(text: str, size: int):
    """按长度切片；空文本返回空串（飞书不允许空文本，调用方已保证非空）。"""
    if not text:
        return [""]
    if len(text) <= size:
        return [text]
    return [text[i : i + size] for i in range(0, len(text), size)]
