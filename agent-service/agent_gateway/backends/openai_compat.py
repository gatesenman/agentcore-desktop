import json
import re
import httpx
from .base import AgentBackend

# 部分模型（如 SiliconFlow 上的 Qwen2.5）流式输出工具调用时会把模板残片 "}\n</tool_call>" 泄漏到 content，
# 污染历史后模型会"只说不做"。这里在输出和历史两侧清洗。
_ARTIFACT = re.compile(r"\n?\}?[ \t\n]*</?tool_call>[ \t\n]*")
_PARTIAL = re.compile(r"(\}[ \t\n]*(<[/a-z_]{0,11})?|<[/a-z_]{0,11})$")


def _clean(text):
    return _ARTIFACT.sub("", text or "")


class _ContentFilter:
    def __init__(self):
        self.buf = ""

    def feed(self, t):
        self.buf = _clean(self.buf + t)
        m = _PARTIAL.search(self.buf)
        cut = m.start() if m and "tool_call>".startswith(m.group(0).partition("<")[2].lstrip("/")) else len(self.buf)
        out, self.buf = self.buf[:cut], self.buf[cut:]
        return out

    def flush(self):
        out, self.buf = self.buf, ""
        return _clean(out)


class OpenAICompatBackend(AgentBackend):
    """Generic backend: any framework/service exposing OpenAI Chat Completions
    (e.g. AgentCoreServer, LangGraph/CrewAI servers, vLLM, DashScope compatible-mode)."""
    name = "openai"

    def _cfg(self):
        import os
        c = {"base_url": os.environ.get("OPENAI_COMPAT_BASE_URL") or os.environ.get("SILICONFLOW_BASE_URL"),
             "api_key": os.environ.get("OPENAI_COMPAT_API_KEY") or os.environ.get("SILICONFLOW_API_KEY"),
             "upstream_model": os.environ.get("OPENAI_COMPAT_MODEL") or os.environ.get("SILICONFLOW_MODEL"),
             **{k: v for k, v in self.config.items() if v}}
        return c

    async def chat(self, body):
        """Transparent passthrough incl. tools / tool_calls deltas."""
        c = self._cfg()
        headers = {"Authorization": f"Bearer {c['api_key']}"} if c.get("api_key") else {}
        req = {k: v for k, v in body.items() if k not in ("stream_options",)}
        req["messages"] = [({**m, "content": _clean(m["content"])} if m.get("role") == "assistant"
                            and isinstance(m.get("content"), str) else m) for m in body.get("messages", [])]
        flt = _ContentFilter()
        req.update(model=c.get("upstream_model") or body.get("model"), stream=True,
                   stream_options={"include_usage": True})
        async with httpx.AsyncClient(timeout=None) as cli:
            async with cli.stream("POST", c["base_url"].rstrip("/") + "/chat/completions", json=req, headers=headers) as r:
                if r.status_code >= 400:
                    from .base import UpstreamError
                    raise UpstreamError(r.status_code, (await r.aread())[:500].decode("utf-8", "replace"))
                async for line in r.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if data == "[DONE]":
                        break
                    obj = json.loads(data)
                    if not obj.get("choices") and not obj.get("usage"):
                        continue
                    for ch in obj.get("choices") or []:
                        d = ch.get("delta") or {}
                        out = {k: d[k] for k in ("content", "tool_calls") if d.get(k)}
                        if "content" in out:
                            out["content"] = flt.feed(out["content"])
                            if not out["content"]:
                                del out["content"]
                        if out:
                            yield out
                    if obj.get("usage"):
                        rest = flt.flush()
                        if rest:
                            yield {"content": rest}
                        u = obj["usage"]
                        yield {"usage": {k: u.get(k, 0) for k in ("prompt_tokens", "completion_tokens", "total_tokens")}}

    async def stream(self, messages, model):
        c = self._cfg()
        headers = {"Authorization": f"Bearer {c.get('api_key', '')}"} if c.get("api_key") else {}
        body = {"model": c.get("upstream_model") or model, "messages": messages, "stream": True}
        async with httpx.AsyncClient(timeout=None) as cli:
            async with cli.stream("POST", c["base_url"].rstrip("/") + "/chat/completions", json=body, headers=headers) as r:
                r.raise_for_status()
                async for line in r.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if data == "[DONE]":
                        break
                    for ch in json.loads(data).get("choices", []):
                        t = (ch.get("delta") or {}).get("content")
                        if t:
                            yield t
