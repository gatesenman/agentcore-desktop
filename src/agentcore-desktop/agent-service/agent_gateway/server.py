"""Agent Gateway: exposes the selected backend as an OpenAI-compatible endpoint
that ZCode's agent runtime consumes as a model provider."""
import json, os, time, uuid
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse, JSONResponse, HTMLResponse
from .backends import REGISTRY


def _load_dotenv():
    for d in filter(None, [os.environ.get("AGENT_GATEWAY_ENV_DIR"), str(Path.home() / ".agentcore-desktop"), str(Path(__file__).parent.parent)]):
      f = Path(d) / ".env"
      if f.exists():
        for line in f.read_text().splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())
        break


_load_dotenv()


_default_cfg = (Path.home() / ".agentcore-desktop" / "gateway.json") if getattr(__import__("sys"), "frozen", False) else (Path(__file__).parent.parent / "gateway.json")
CONFIG_PATH = Path(os.environ.get("AGENT_GATEWAY_CONFIG", str(_default_cfg)))
CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)


def load_config() -> dict:
    path = str(CONFIG_PATH)
    cfg = json.loads(Path(path).read_text()) if Path(path).exists() else {}
    name = cfg.get("backend") if cfg.get("_ui_selected") else (os.environ.get("AGENT_BACKEND") or cfg.get("backend"))
    if not name:  # auto: real model when a key exists, else mock
        has_key = os.environ.get("DASHSCOPE_API_KEY") or os.environ.get("SILICONFLOW_API_KEY") or os.environ.get("OPENAI_COMPAT_API_KEY")
        name = "agentscope" if has_key else "mock"
    return {"backend": name, **cfg.get("backends", {}).get(name, {})}


CFG = load_config()
BACKEND = REGISTRY[CFG["backend"]](CFG)
app = FastAPI()
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402

# 仅允许本机界面（Vite dev / Electron file:// / 本机端口）访问管理接口。
app.add_middleware(CORSMiddleware, allow_origin_regex=r"^(null|file://.*|app://.*|https?://(localhost|127\.0\.0\.1)(:\d+)?)$",
                   allow_methods=["*"], allow_headers=["*"])


@app.get("/v1/models")
async def models():
    return {"object": "list", "data": [{"id": "agent-gateway", "object": "model"}]}


@app.get("/healthz")
async def health():
    return {"ok": True, "backend": BACKEND.name}


@app.post("/v1/chat/completions")
async def chat(req: Request):
    body = await req.json()
    if os.environ.get("AGENT_GATEWAY_DUMP"):
        Path(os.environ["AGENT_GATEWAY_DUMP"]).write_text(json.dumps(body, ensure_ascii=False)[:200000])
    msgs, model, cid = body.get("messages", []), body.get("model", "agent-gateway"), "chatcmpl-" + uuid.uuid4().hex

    def chunk(delta, finish=None):
        return {"id": cid, "object": "chat.completion.chunk", "created": int(time.time()), "model": model,
                "choices": [{"index": 0, "delta": delta, "finish_reason": finish}]}

    if not body.get("stream"):
        text, calls = "", []
        usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
        try:
            parts = [d async for d in BACKEND.chat(body)]
        except Exception as e:  # noqa: BLE001
            status = getattr(e, "status", None) or getattr(e, "status_code", None) or 502
            return JSONResponse({"error": {"message": str(e)[:500], "type": "upstream_error", "code": status}},
                                status_code=status if 400 <= status < 600 else 502)
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
        return JSONResponse({"id": cid, "object": "chat.completion", "created": int(time.time()), "model": model,
                             "choices": [{"index": 0, "message": msg, "finish_reason": "tool_calls" if calls else "stop"}],
                             "usage": usage})

    stream_it = BACKEND.chat(body).__aiter__()
    try:  # 先取第一段：开流前的错误映射成真实 HTTP 状态码（429/401/502…）
        first = await stream_it.__anext__()
    except StopAsyncIteration:
        first = None
    except Exception as e:  # noqa: BLE001
        status = getattr(e, "status", None) or getattr(e, "status_code", None) or 502
        return JSONResponse({"error": {"message": str(e)[:500], "type": "upstream_error", "code": status}},
                            status_code=status if 400 <= status < 600 else 502)

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
                                fh.write(f"{BACKEND.name}\t{n}\n")
                yield f"data: {json.dumps(chunk(d), ensure_ascii=False)}\n\n"
        except Exception as e:  # noqa: BLE001  流中途出错：发 OpenAI 风格 error 事件
            yield f"data: {json.dumps({'error': {'message': str(e)[:500], 'type': 'upstream_error'}}, ensure_ascii=False)}\n\n"
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
            async for d in BACKEND.chat(body):
                if d.get("content"):
                    yield ev(type="TEXT_MESSAGE_CONTENT", messageId=mid, delta=d["content"])
                for tc in d.get("tool_calls", []):
                    if tc.get("id"):
                        yield ev(type="TOOL_CALL_START", toolCallId=tc["id"], toolCallName=tc["function"]["name"], parentMessageId=mid)
                        last = tc["id"]
                    if tc.get("function", {}).get("arguments"):
                        yield ev(type="TOOL_CALL_ARGS", toolCallId=tc.get("id") or last, delta=tc["function"]["arguments"])
            yield ev(type="TEXT_MESSAGE_END", messageId=mid)
            yield ev(type="RUN_FINISHED", threadId=tid, runId=rid)
        except Exception as e:  # noqa: BLE001
            yield ev(type="RUN_ERROR", message=str(e))

    return StreamingResponse(gen(), media_type="text/event-stream")


# ---------------- 后端选择设置（热切换 + 持久化到 gateway.json） ----------------
SETTINGS_HTML = """<!doctype html><meta charset=utf-8><title>AgentCore Desktop · Agent 后端设置</title>
<style>body{font:14px system-ui;background:#1b1b1b;color:#ddd;max-width:640px;margin:40px auto}select,input,button{font:inherit;padding:6px;margin:4px 0;width:100%;box-sizing:border-box}label{display:block;margin-top:12px;color:#aaa}button{background:#3b82f6;color:#fff;border:0;border-radius:6px;cursor:pointer}</style>
<h2>Agent 后端设置</h2><p>当前：<b id=cur></b></p>
<label>后端<select id=backend></select></label>
<label>backend 配置（JSON，可留空；密钥建议放 .env）<textarea id=cfg rows=8 style="width:100%"></textarea></label>
<button onclick=save()>保存并切换</button><p id=msg></p>
<script>
async function load(){const r=await (await fetch('/admin/backend')).json();cur.textContent=r.backend;
backend.innerHTML=r.available.map(b=>`<option ${b==r.backend?'selected':''}>${b}</option>`).join('');cfg.value=JSON.stringify(r.config||{},null,2)}
async function save(){const r=await fetch('/admin/backend',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({backend:backend.value,config:JSON.parse(cfg.value||'{}')})});msg.textContent=r.ok?'已切换（新会话/下一条消息生效）':'失败：'+await r.text();load()}
load()</script>"""


@app.get("/settings")
async def settings_page():
    return HTMLResponse(SETTINGS_HTML)


SECRET_KEYS = ("api_key", "token", "access_key_id", "access_key_secret", "debug_token")


def _read_cfg_file() -> dict:
    return json.loads(CONFIG_PATH.read_text()) if CONFIG_PATH.exists() else {}


@app.get("/admin/backend")
async def get_backend(name: str | None = None):
    data = _read_cfg_file()
    sel = name or BACKEND.name
    raw = data.get("backends", {}).get(sel, {}) if sel != BACKEND.name or not CFG else {**data.get("backends", {}).get(sel, {}), **{k: v for k, v in CFG.items() if k != "backend"}}
    return {"backend": BACKEND.name, "selected": sel, "available": sorted(REGISTRY),
            "config": {k: v for k, v in raw.items() if k not in SECRET_KEYS and not k.startswith("_")},
            "secrets_set": [k for k in SECRET_KEYS if raw.get(k)]}


@app.post("/admin/backend")
async def set_backend(req: Request):
    global CFG, BACKEND
    # 强制 JSON：浏览器跨站“简单请求”无法携带该类型（会触发被 CORS 拒绝的预检），防 CSRF 改配置。
    if "application/json" not in req.headers.get("content-type", ""):
        return JSONResponse({"error": "content-type must be application/json"}, status_code=415)
    body = await req.json()
    name = body.get("backend")
    if name not in REGISTRY:
        return JSONResponse({"error": f"unknown backend {name}"}, status_code=400)
    data = _read_cfg_file()
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
    CONFIG_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2))
    try:
        os.chmod(CONFIG_PATH, 0o600)
    except OSError:
        pass
    CFG = {"backend": name, **merged}
    BACKEND = REGISTRY[name](CFG)
    return {"ok": True, "backend": name}


# ---------------- 本地“云”桩：替代智谱云端接口，保证不访问外网 ----------------
@app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
async def local_cloud_stub(path: str):
    return JSONResponse({"code": 404, "success": False, "msg": "disabled in AgentCore Desktop (offline)", "data": None},
                        status_code=404)
