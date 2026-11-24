"""Agent Gateway: exposes the selected backend as an OpenAI-compatible endpoint
that ZCode's agent runtime consumes as a model provider."""
from __future__ import annotations

import json
import os
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse

from .backends import REGISTRY
from .backends.base import AgentBackend
from .errors import public_error
from .presets import BACKEND_LABELS, list_presets


def _load_dotenv() -> None:
    """Load the first existing .env. Never logs values. Uses setdefault so process env wins."""
    candidates = filter(
        None,
        [
            os.environ.get("AGENT_GATEWAY_ENV_DIR"),
            str(Path.home() / ".agentcore-desktop"),
            str(Path(__file__).parent.parent),
        ],
    )
    for d in candidates:
        f = Path(d) / ".env"
        if not f.exists():
            continue
        for line in f.read_text().splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
        break


def default_config_path() -> Path:
    if os.environ.get("AGENT_GATEWAY_CONFIG"):
        return Path(os.environ["AGENT_GATEWAY_CONFIG"])
    if getattr(__import__("sys"), "frozen", False):
        return Path.home() / ".agentcore-desktop" / "gateway.json"
    return Path(__file__).parent.parent / "gateway.json"


def load_config(config_path: Path, environ: dict[str, str] | None = None) -> dict:
    """Resolve the active backend + its settings. Unknown names fail clearly (not KeyError)."""
    env = environ if environ is not None else os.environ
    cfg: dict = {}
    path = Path(config_path)
    if path.exists():
        cfg = json.loads(path.read_text())
    name = cfg.get("backend") if cfg.get("_ui_selected") else (env.get("AGENT_BACKEND") or cfg.get("backend"))
    if not name:  # auto: real model when a key exists, else mock
        has_key = env.get("DASHSCOPE_API_KEY") or env.get("SILICONFLOW_API_KEY") or env.get("OPENAI_COMPAT_API_KEY")
        name = "agentscope" if has_key else "mock"
    if name not in REGISTRY:
        available = ", ".join(sorted(REGISTRY))
        raise ValueError(f"未知后端 {name!r}。可选：{available}")
    return {"backend": name, **cfg.get("backends", {}).get(name, {})}


@dataclass
class GatewayRuntime:
    config_path: Path
    cfg: dict
    backend: AgentBackend
    started_at: float = field(default_factory=time.time)
    last_error: str | None = None

    def apply_backend(self, name: str, merged: dict) -> None:
        self.cfg = {"backend": name, **merged}
        self.backend = REGISTRY[name](self.cfg)


def create_runtime(
    *,
    config_path: Path | None = None,
    config: dict | None = None,
    load_env: bool = True,
    environ: dict[str, str] | None = None,
) -> GatewayRuntime:
    if load_env:
        _load_dotenv()
    path = Path(config_path) if config_path is not None else default_config_path()
    cfg = dict(config) if config is not None else load_config(path, environ)
    name = cfg.get("backend", "mock")
    if name not in REGISTRY:
        available = ", ".join(sorted(REGISTRY))
        raise ValueError(f"未知后端 {name!r}。可选：{available}")
    return GatewayRuntime(config_path=path, cfg=cfg, backend=REGISTRY[name](cfg))


SECRET_KEYS = ("api_key", "token", "access_key_id", "access_key_secret", "debug_token")


def _read_cfg_file(path: Path) -> dict:
    return json.loads(path.read_text()) if path.exists() else {}


def create_app(runtime: GatewayRuntime | None = None, **runtime_kwargs) -> FastAPI:
    """Build the ASGI app. Tests should pass load_env=False and a temp config_path."""
    rt = runtime or create_runtime(**runtime_kwargs)
    app = FastAPI(title="AgentCore Desktop Gateway")
    app.state.gw = rt

    # 仅允许本机界面（Vite dev / Electron file:// / 本机端口）访问管理接口。
    app.add_middleware(
        CORSMiddleware,
        allow_origin_regex=r"^(null|file://.*|app://.*|https?://(localhost|127\.0\.0\.1)(:\d+)?)$",
        allow_methods=["*"],
        allow_headers=["*"],
    )

    def gw() -> GatewayRuntime:
        return app.state.gw

    @app.get("/v1/models")
    async def models():
        ids = gw().backend.models() or ["agent-gateway"]
        return {"object": "list", "data": [{"id": mid, "object": "model"} for mid in ids]}

    @app.get("/healthz")
    async def health():
        return {
            "ok": True,
            "backend": gw().backend.name,
            "uptime_s": int(time.time() - gw().started_at),
            "last_error": gw().last_error,
        }

    @app.post("/v1/chat/completions")
    async def chat(req: Request):
        body = await req.json()
        if os.environ.get("AGENT_GATEWAY_DUMP"):
            Path(os.environ["AGENT_GATEWAY_DUMP"]).write_text(json.dumps(body, ensure_ascii=False)[:200000])
        msgs, model, cid = body.get("messages", []), body.get("model", "agent-gateway"), "chatcmpl-" + uuid.uuid4().hex

        def chunk(delta, finish=None):
            return {
                "id": cid,
                "object": "chat.completion.chunk",
                "created": int(time.time()),
                "model": model,
                "choices": [{"index": 0, "delta": delta, "finish_reason": finish}],
            }

        if not body.get("stream"):
            text, calls = "", []
            usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
            try:
                parts = [d async for d in gw().backend.chat(body)]
            except Exception as e:  # noqa: BLE001
                status, message = public_error(e)
                gw().last_error = message
                return JSONResponse(
                    {"error": {"message": message, "type": "upstream_error", "code": status}},
                    status_code=status,
                )
            for d in parts:
                usage = d.get("usage") or usage
                text += d.get("content", "")
                for tc in d.get("tool_calls", []):  # merge streamed fragments by index
                    i = tc.get("index", len(calls))
                    while len(calls) <= i:
                        calls.append({"id": None, "type": "function", "function": {"name": "", "arguments": ""}})
                    c = calls[i]
                    c["id"] = tc.get("id") or c["id"]
                    f = tc.get("function") or {}
                    c["function"]["name"] += f.get("name") or ""
                    c["function"]["arguments"] += f.get("arguments") or ""
            msg = {"role": "assistant", "content": text or None}
            if calls:
                msg["tool_calls"] = calls
            return JSONResponse(
                {
                    "id": cid,
                    "object": "chat.completion",
                    "created": int(time.time()),
                    "model": model,
                    "choices": [{"index": 0, "message": msg, "finish_reason": "tool_calls" if calls else "stop"}],
                    "usage": usage,
                }
            )

        stream_it = gw().backend.chat(body).__aiter__()
        try:  # 先取第一段：开流前的错误映射成真实 HTTP 状态码（429/401/502…）
            first = await stream_it.__anext__()
        except StopAsyncIteration:
            first = None
        except Exception as e:  # noqa: BLE001
            status, message = public_error(e)
            gw().last_error = message
            return JSONResponse(
                {"error": {"message": message, "type": "upstream_error", "code": status}},
                status_code=status,
            )

        async def items():
            if first is not None:
                yield first
            async for d in stream_it:
                yield d

        async def gen():
            yield f"data: {json.dumps(chunk({'role': 'assistant', 'content': ''}))}\n\n"
            saw_tools = False
            usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
            try:
                async for d in items():
                    if "usage" in d:  # 后端回传的真实用量
                        usage = d.pop("usage") or usage
                        if not d:
                            continue
                    saw_tools = saw_tools or bool(d.get("tool_calls"))
                    if d.get("tool_calls") and os.environ.get("AGENT_GATEWAY_TOOLLOG"):
                        with open(os.environ["AGENT_GATEWAY_TOOLLOG"], "a") as fh:
                            for tc in d["tool_calls"]:
                                n = (tc.get("function") or {}).get("name")
                                if n:
                                    fh.write(f"{gw().backend.name}\t{n}\n")
                    yield f"data: {json.dumps(chunk(d), ensure_ascii=False)}\n\n"
            except Exception as e:  # noqa: BLE001  流中途出错：发 OpenAI 风格 error 事件
                status, message = public_error(e)
                gw().last_error = message
                yield f"data: {json.dumps({'error': {'message': message, 'type': 'upstream_error', 'code': status}}, ensure_ascii=False)}\n\n"
                yield "data: [DONE]\n\n"
                return
            final = chunk({}, "tool_calls" if saw_tools else "stop")
            final["usage"] = usage
            yield f"data: {json.dumps(final)}\n\ndata: [DONE]\n\n"

        return StreamingResponse(gen(), media_type="text/event-stream")

    @app.post("/agui")
    async def agui(req: Request):
        """AG-UI server endpoint: exposes the selected backend over AG-UI too (for AG-UI clients / tests)."""
        run = await req.json()
        tid, rid, mid = run.get("threadId", "t"), run.get("runId", "r"), uuid.uuid4().hex
        msgs = [{"role": m["role"], "content": m.get("content", "")} for m in run.get("messages", [])]
        tools = [{"type": "function", "function": t} for t in run.get("tools", [])]
        body = {"messages": msgs, **({"tools": tools} if tools else {})}

        def ev(**e):
            return f"data: {json.dumps(e, ensure_ascii=False)}\n\n"

        async def gen():
            yield ev(type="RUN_STARTED", threadId=tid, runId=rid)
            yield ev(type="TEXT_MESSAGE_START", messageId=mid, role="assistant")
            try:
                async for d in gw().backend.chat(body):
                    if d.get("content"):
                        yield ev(type="TEXT_MESSAGE_CONTENT", messageId=mid, delta=d["content"])
                    for tc in d.get("tool_calls", []):
                        if tc.get("id"):
                            yield ev(
                                type="TOOL_CALL_START",
                                toolCallId=tc["id"],
                                toolCallName=tc["function"]["name"],
                                parentMessageId=mid,
                            )
                            last = tc["id"]
                        if tc.get("function", {}).get("arguments"):
                            yield ev(
                                type="TOOL_CALL_ARGS",
                                toolCallId=tc.get("id") or last,
                                delta=tc["function"]["arguments"],
                            )
                yield ev(type="TEXT_MESSAGE_END", messageId=mid)
                yield ev(type="RUN_FINISHED", threadId=tid, runId=rid)
            except Exception as e:  # noqa: BLE001
                _status, message = public_error(e)
                gw().last_error = message
                yield ev(type="RUN_ERROR", message=message)

        return StreamingResponse(gen(), media_type="text/event-stream")

    settings_html = """<!doctype html><meta charset=utf-8><title>AgentCore Desktop · Agent 后端设置</title>
<style>body{font:14px system-ui;background:#1b1b1b;color:#ddd;max-width:720px;margin:40px auto;line-height:1.5}select,input,button,textarea{font:inherit;padding:6px;margin:4px 0;width:100%;box-sizing:border-box}label{display:block;margin-top:12px;color:#aaa}button{background:#3b82f6;color:#fff;border:0;border-radius:6px;cursor:pointer}button.secondary{background:#334155;margin-right:8px;width:auto}#presets{display:flex;flex-wrap:wrap;gap:8px;margin:8px 0}.hint{color:#9ca3af;font-size:12px}</style>
<h2>Agent 后端设置</h2>
<p>当前：<b id=cur></b></p>
<p class="hint">密钥请写在 <code>.env</code> 或 <code>~/.agentcore-desktop/.env</code>，不要粘贴到下面的 JSON 里，也不要提交到 Git。</p>
<label>快捷预设</label>
<div id=presets></div>
<label>后端<select id=backend></select></label>
<label>backend 配置（JSON，可留空；不要填写 api_key）<textarea id=cfg rows=8 style="width:100%"></textarea></label>
<button onclick=save()>保存并切换</button><p id=msg></p>
<script>
async function load(){
  const r=await (await fetch('/admin/backend')).json();
  const p=await (await fetch('/admin/presets')).json();
  cur.textContent=(r.backend_label||r.backend)+' ('+r.backend+')';
  backend.innerHTML=r.available.map(b=>`<option value="${b}" ${b==r.backend?'selected':''}>${(r.labels&&r.labels[b])||b}</option>`).join('');
  cfg.value=JSON.stringify(r.config||{},null,2);
  presets.innerHTML=p.presets.map(x=>`<button class=secondary type=button onclick='applyPreset(${JSON.stringify(x.id)})'>${x.label}</button>`).join('');
  window.__presets=p.presets;
}
async function applyPreset(id){
  const spec=(window.__presets||[]).find(x=>x.id===id);
  if(!spec)return;
  backend.value=spec.backend;
  cfg.value=JSON.stringify(spec.config||{},null,2);
  msg.textContent='已套用预设「'+spec.label+'」。请确认后点击保存。密钥仍应放在 .env。';
}
async function save(){
  const r=await fetch('/admin/backend',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({backend:backend.value,config:JSON.parse(cfg.value||'{}')})});
  msg.textContent=r.ok?'已切换（新会话/下一条消息生效）':'失败：'+await r.text();
  load();
}
load()
</script>"""


    @app.get("/settings")
    async def settings_page():
        return HTMLResponse(settings_html)

    @app.get("/admin/presets")
    async def get_presets():
        return list_presets()

    @app.get("/admin/backend")
    async def get_backend(name: str | None = None):
        data = _read_cfg_file(gw().config_path)
        sel = name or gw().backend.name
        raw = (
            data.get("backends", {}).get(sel, {})
            if sel != gw().backend.name or not gw().cfg
            else {
                **data.get("backends", {}).get(sel, {}),
                **{k: v for k, v in gw().cfg.items() if k != "backend"},
            }
        )
        return {
            "backend": gw().backend.name,
            "backend_label": BACKEND_LABELS.get(gw().backend.name, gw().backend.name),
            "selected": sel,
            "available": sorted(REGISTRY),
            "labels": {name: BACKEND_LABELS.get(name, name) for name in REGISTRY},
            "config": {k: v for k, v in raw.items() if k not in SECRET_KEYS and not k.startswith("_")},
            "secrets_set": [k for k in SECRET_KEYS if raw.get(k)],
        }

    @app.post("/admin/backend")
    async def set_backend(req: Request):
        # 强制 JSON：浏览器跨站“简单请求”无法携带该类型（会触发被 CORS 拒绝的预检），防 CSRF 改配置。
        if "application/json" not in req.headers.get("content-type", ""):
            return JSONResponse({"error": "content-type must be application/json"}, status_code=415)
        body = await req.json()
        name = body.get("backend")
        if name not in REGISTRY:
            return JSONResponse({"error": f"未知后端 {name}。可选：{', '.join(sorted(REGISTRY))}"}, status_code=400)
        data = _read_cfg_file(gw().config_path)
        data["backend"] = name
        data["_ui_selected"] = True
        merged = {**data.get("backends", {}).get(name, {})}
        for k, v in (body.get("config") or {}).items():
            if k in SECRET_KEYS and not v:
                continue  # 留空保持原值
            if v == "":
                merged.pop(k, None)
            else:
                merged[k] = v
        data.setdefault("backends", {})[name] = merged
        gw().config_path.parent.mkdir(parents=True, exist_ok=True)
        gw().config_path.write_text(json.dumps(data, ensure_ascii=False, indent=2))
        try:
            os.chmod(gw().config_path, 0o600)
        except OSError:
            pass
        gw().apply_backend(name, merged)
        return {"ok": True, "backend": name}

    # ---------------- 本地“云”桩：替代智谱云端接口，保证不访问外网 ----------------
    @app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
    async def local_cloud_stub(path: str):
        return JSONResponse(
            {"code": 404, "success": False, "msg": "disabled in AgentCore Desktop (offline)", "data": None},
            status_code=404,
        )

    return app


class _LazyApp:
    """Delay dotenv / config load until the first ASGI call so tests can import create_app safely."""

    def __init__(self) -> None:
        self._app: FastAPI | None = None

    def _ensure(self) -> FastAPI:
        if self._app is None:
            self._app = create_app()
        return self._app

    def __getattr__(self, name: str):
        return getattr(self._ensure(), name)

    async def __call__(self, scope, receive, send):
        await self._ensure()(scope, receive, send)


app = _LazyApp()
