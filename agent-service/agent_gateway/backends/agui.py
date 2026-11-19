"""AG-UI backend: talk to any agent server speaking the AG-UI protocol
(AgentCore AGUI service, CopilotKit/LangGraph/CrewAI/Mastra AG-UI endpoints, ...)."""
import json, os, uuid
import httpx
from .base import AgentBackend


class AGUIBackend(AgentBackend):
    name = "agui"

    async def chat(self, body):
        url = self.config.get("url") or os.environ["AGUI_URL"]
        token = self.config.get("token") or os.environ.get("AGUI_TOKEN")
        msgs = []
        for m in body.get("messages", []):
            mm = {"id": uuid.uuid4().hex, "role": m["role"], "content": m.get("content") if isinstance(m.get("content"), str) else
                  "".join(p.get("text", "") for p in (m.get("content") or []) if isinstance(p, dict))}
            if m.get("tool_calls"):
                mm["toolCalls"] = m["tool_calls"]
            if m["role"] == "tool":
                mm["toolCallId"] = m.get("tool_call_id")
            msgs.append(mm)
        tools = [{"name": t["function"]["name"], "description": t["function"].get("description", ""),
                  "parameters": t["function"].get("parameters", {})} for t in body.get("tools") or []]
        run = {"threadId": self.config.get("thread_id") or uuid.uuid4().hex, "runId": uuid.uuid4().hex,
               "messages": msgs, "tools": tools, "state": {}, "context": [], "forwardedProps": {}}
        headers = {"Accept": "text/event-stream", **({"Authorization": f"Bearer {token}"} if token else {})}
        idx = {}
        async with httpx.AsyncClient(timeout=None) as cli:
            async with cli.stream("POST", url, json=run, headers=headers) as r:
                r.raise_for_status()
                async for line in r.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    ev = json.loads(line[5:].strip())
                    t = ev.get("type")
                    if t in ("TEXT_MESSAGE_CONTENT", "TEXT_MESSAGE_CHUNK") and ev.get("delta"):
                        yield {"content": ev["delta"]}
                    elif t in ("TOOL_CALL_START", "TOOL_CALL_CHUNK") and ev.get("toolCallId") not in idx and ev.get("toolCallName"):
                        idx[ev["toolCallId"]] = len(idx)
                        yield {"tool_calls": [{"index": idx[ev["toolCallId"]], "id": ev["toolCallId"], "type": "function",
                                               "function": {"name": ev["toolCallName"], "arguments": ev.get("delta", "")}}]}
                    elif t == "TOOL_CALL_ARGS":
                        yield {"tool_calls": [{"index": idx.get(ev["toolCallId"], 0), "function": {"arguments": ev.get("delta", "")}}]}
                    elif t == "RUN_ERROR":
                        raise RuntimeError(ev.get("message", "AG-UI run error"))
                    elif t == "RUN_FINISHED":
                        break

    async def stream(self, messages, model):
        async for d in self.chat({"messages": messages}):
            if d.get("content"):
                yield d["content"]
