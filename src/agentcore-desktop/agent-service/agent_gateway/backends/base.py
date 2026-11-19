"""Pluggable backend interface. Every agent framework plugs in by implementing AgentBackend."""
from __future__ import annotations
from abc import ABC, abstractmethod
from typing import AsyncIterator

Message = dict  # OpenAI-style {"role": ..., "content": ...}


class AgentBackend(ABC):
    name: str = "base"

    def __init__(self, config: dict):
        self.config = config

    @abstractmethod
    def stream(self, messages: list[Message], model: str) -> AsyncIterator[str]:
        """Yield assistant text chunks for the conversation."""

    async def chat(self, body: dict) -> AsyncIterator[dict]:
        """Full OpenAI-compatible turn. Yields OpenAI `delta` dicts: {"content": str} or
        {"tool_calls": [...]}. Default: text-only via stream(). Override for tool-call passthrough."""
        async for t in self.stream(body.get("messages", []), body.get("model", "")):
            yield {"content": t}

    def models(self) -> list[str]:
        return [self.config.get("model_id") or self.name]


def text_of(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(p.get("text", "") for p in content if isinstance(p, dict))
    return str(content or "")


class UpstreamError(RuntimeError):
    """上游模型服务返回的 HTTP 错误；网关原样映射状态码（429 等），便于 ZCode 正确重试/提示。"""

    def __init__(self, status: int, detail: str):
        super().__init__(f"upstream {status}: {detail}")
        self.status = status
        self.detail = detail
