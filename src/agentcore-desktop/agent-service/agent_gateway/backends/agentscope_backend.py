import os
from .base import AgentBackend, text_of


class AgentScopeBackend(AgentBackend):
    """AgentScope 2.x Agent (ReAct loop). Model provider selectable via config `model_provider`:
    - "dashscope" (default when DASHSCOPE_API_KEY set): 阿里云百炼
    - "openai": any OpenAI-compatible endpoint (SiliconFlow, AgentCore model gateway, vLLM ...)
    AgentCore managed resources (MCP/memory/credentials) can be attached via alibabacloud-agentcore-sdk
    integrations (`agentcore.integrations.agentscope`) once AK + workspace are configured."""
    name = "agentscope"

    def _model(self):
        c = self.config
        provider = c.get("model_provider") or ("dashscope" if os.environ.get("DASHSCOPE_API_KEY") else "openai")
        if provider == "dashscope":
            from agentscope.credential import DashScopeCredential
            from agentscope.model import DashScopeChatModel
            return DashScopeChatModel(
                credential=DashScopeCredential(api_key=c.get("api_key") or os.environ["DASHSCOPE_API_KEY"]),
                model=c.get("model") or "qwen-plus", stream=False)
        from agentscope.credential import OpenAICredential
        from agentscope.model import OpenAIChatModel
        return OpenAIChatModel(
            credential=OpenAICredential(
                api_key=c.get("api_key") or os.environ.get("OPENAI_COMPAT_API_KEY") or os.environ["SILICONFLOW_API_KEY"],
                base_url=c.get("base_url") or os.environ.get("OPENAI_COMPAT_BASE_URL") or os.environ.get("SILICONFLOW_BASE_URL")),
            model=c.get("model") or os.environ.get("OPENAI_COMPAT_MODEL") or os.environ.get("SILICONFLOW_MODEL"),
            stream=False)

    async def stream(self, messages, model):
        from agentscope.agent import Agent
        from agentscope.message import Msg, TextBlock

        agent = Agent(name="assistant",
                      system_prompt=self.config.get("sys_prompt", "You are a helpful assistant."),
                      model=self._model())
        inputs = [Msg(name=m["role"], role=m["role"],
                      content=[TextBlock(text=text_of(m.get("content")))] + _image_blocks(m.get("content")))
                  for m in messages if m.get("role") in ("user", "assistant") and text_of(m.get("content"))]
        reply = await agent.reply(inputs)
        self._last_usage = getattr(reply, "usage", None)
        yield reply.get_text_content() or ""

    # ---- tool-call passthrough: ZCode owns the tool loop, AgentScope owns the model step ----
    @staticmethod
    def _to_msgs(messages):
        from agentscope.message import Msg, TextBlock, ToolCallBlock, ToolResultBlock, ToolResultState
        out = []
        for m in messages:
            role = m.get("role")
            if role == "tool":
                blk = ToolResultBlock(id=m.get("tool_call_id", ""), name=m.get("name") or "tool",
                                      output=text_of(m.get("content")), state=ToolResultState.SUCCESS)
                if out and out[-1].role == "assistant":
                    out[-1].content.append(blk)
                else:
                    out.append(Msg(name="assistant", role="assistant", content=[blk]))
                continue
            if role not in ("system", "user", "assistant"):
                continue
            blocks = []
            if text_of(m.get("content")):
                blocks.append(TextBlock(text=text_of(m.get("content"))))
            blocks += _image_blocks(m.get("content"))
            for tc in m.get("tool_calls") or []:
                f = tc.get("function", {})
                blocks.append(ToolCallBlock(id=tc.get("id", ""), name=f.get("name", ""), input=f.get("arguments") or "{}"))
            if blocks:
                out.append(Msg(name=role, role=role, content=blocks))
        return out

    async def chat(self, body):
        if not body.get("tools"):
            async for d in super().chat(body):
                yield d
            u = getattr(self, "_last_usage", None)
            if u:
                yield {"usage": {"prompt_tokens": u.input_tokens, "completion_tokens": u.output_tokens,
                                 "total_tokens": u.input_tokens + u.output_tokens}}
            return
        from agentscope.message import TextBlock, ToolCallBlock
        model = self._model()
        resp = await model(self._to_msgs(body.get("messages", [])), tools=body["tools"])
        if not hasattr(resp, "content"):  # streaming generator: keep last (complete) chunk
            last = None
            async for last in resp:
                pass
            resp = last
        calls = []
        for b in resp.content:
            if isinstance(b, TextBlock) and b.text:
                yield {"content": b.text}
            elif isinstance(b, ToolCallBlock):
                calls.append({"index": len(calls), "id": b.id, "type": "function",
                              "function": {"name": b.name, "arguments": b.input or "{}"}})
        if calls:
            yield {"tool_calls": calls}
        u = getattr(resp, "usage", None)
        if u:
            yield {"usage": {"prompt_tokens": u.input_tokens, "completion_tokens": u.output_tokens,
                             "total_tokens": u.input_tokens + u.output_tokens}}


def _image_blocks(content):
    """OpenAI image_url 内容 → AgentScope DataBlock（data: URL 转 base64，其余按 URL）。"""
    from agentscope.message import DataBlock, Base64Source, URLSource
    out = []
    if not isinstance(content, list):
        return out
    for part in content:
        if not isinstance(part, dict) or part.get("type") != "image_url":
            continue
        url = (part.get("image_url") or {}).get("url", "")
        if url.startswith("data:") and ";base64," in url:
            head, data = url.split(";base64,", 1)
            out.append(DataBlock(source=Base64Source(data=data, media_type=head[5:] or "image/png")))
        elif url:
            out.append(DataBlock(source=URLSource(url=url, media_type="image/*")))
    return out
