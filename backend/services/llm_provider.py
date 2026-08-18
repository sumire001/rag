"""模型适配层。

对上层只暴露两个能力：
    complete(messages) -> str            一次性返回
    stream(messages)   -> Iterator[str]  逐段返回

换模型只需要在这里加一个 Provider，业务代码不用动。
"""

import json
import time
from typing import Iterator, List

import requests

from services import runtime_config

# 请求模型服务的超时时间（秒）
LLM_TIMEOUT = 60


class LLMError(Exception):
    pass


class BaseProvider:
    def complete(self, messages: List[dict]) -> str:
        return "".join(self.stream(messages))

    def stream(self, messages: List[dict]) -> Iterator[str]:
        raise NotImplementedError


class EchoProvider(BaseProvider):
    """离线回声模式：不依赖任何外部服务，方便先把前后端链路跑通。"""

    def stream(self, messages: List[dict]) -> Iterator[str]:
        last_user = ""
        for m in reversed(messages):
            if m.get("role") == "user":
                last_user = m.get("content", "")
                break

        reply = (
            f"我收到了你的消息：「{last_user}」\n\n"
            f"当前是 echo 离线模式，没有接真实模型。\n"
            f"本轮上下文共 {len(messages)} 条消息。\n"
            f"把 backend/.env 里的 LLM_PROVIDER 改成 openai 并填上 LLM_API_KEY，即可切换到真实模型。"
        )

        # 模拟打字机效果，每次吐几个字符
        step = 3
        for i in range(0, len(reply), step):
            yield reply[i:i + step]
            time.sleep(0.02)


class OpenAICompatProvider(BaseProvider):
    """任何 OpenAI 兼容的 /chat/completions 接口都能用。"""

    def __init__(self):
        api_key = runtime_config.get("api_key")
        if not api_key:
            raise LLMError("未配置 LLM_API_KEY，请在页面左下角「设置」中填写")
        self.url = runtime_config.get("base_url").rstrip("/") + "/chat/completions"
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

    def _payload(self, messages: List[dict], stream: bool) -> dict:
        return {
            "model": runtime_config.get("model"),
            "messages": messages,
            "temperature": runtime_config.get("temperature"),
            "stream": stream,
        }

    def complete(self, messages: List[dict]) -> str:
        try:
            resp = requests.post(
                self.url,
                headers=self.headers,
                json=self._payload(messages, False),
                timeout=LLM_TIMEOUT,
            )
        except requests.RequestException as e:
            raise LLMError(f"请求模型服务失败: {e}") from e

        if resp.status_code != 200:
            raise LLMError(f"模型服务返回 {resp.status_code}: {resp.text[:200]}")
        data = resp.json()
        return data["choices"][0]["message"]["content"]

    def stream(self, messages: List[dict]) -> Iterator[str]:
        try:
            resp = requests.post(
                self.url,
                headers=self.headers,
                json=self._payload(messages, True),
                timeout=LLM_TIMEOUT,
                stream=True,
            )
        except requests.RequestException as e:
            raise LLMError(f"请求模型服务失败: {e}") from e

        if resp.status_code != 200:
            raise LLMError(f"模型服务返回 {resp.status_code}: {resp.text[:200]}")

        for raw in resp.iter_lines(decode_unicode=True):
            if not raw or not raw.startswith("data:"):
                continue
            chunk = raw[5:].strip()
            if chunk == "[DONE]":
                break
            try:
                delta = json.loads(chunk)["choices"][0].get("delta", {})
            except (json.JSONDecodeError, KeyError, IndexError):
                continue
            piece = delta.get("content")
            if piece:
                yield piece


def get_provider() -> BaseProvider:
    name = (runtime_config.get("provider") or "echo").lower()
    if name == "openai":
        return OpenAICompatProvider()
    return EchoProvider()
