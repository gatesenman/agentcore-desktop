"""Health, streaming mid-error, and bind-host contract tests. No API keys."""
from __future__ import annotations

import json

from fastapi.testclient import TestClient

from agent_gateway.backends.base import AgentBackend, UpstreamError
from agent_gateway.server import create_app
from run_gateway import validate_bind_host
import pytest


class FailingBackend(AgentBackend):
    name = "mock"

    def __init__(self, config, exc, mid_stream=False):
        super().__init__(config)
        self.exc = exc
        self.mid_stream = mid_stream

    async def stream(self, messages, model):
        if self.mid_stream:
            yield "partial"
            raise self.exc
        raise self.exc

    async def chat(self, body):
        async for t in self.stream(body.get("messages", []), body.get("model", "")):
            yield {"content": t}


def test_non_stream_maps_401_to_chinese_and_records_last_error(tmp_path):
    cfg = tmp_path / "gateway.json"
    cfg.write_text('{"backend":"mock"}', encoding="utf-8")
    app = create_app(config_path=cfg, config={"backend": "mock"}, load_env=False)
    app.state.gw.backend = FailingBackend({}, UpstreamError(401, "nope"))
    with TestClient(app) as client:
        r = client.post(
            "/v1/chat/completions",
            json={"stream": False, "messages": [{"role": "user", "content": "hi"}]},
        )
        assert r.status_code == 401
        assert "认证失败" in r.json()["error"]["message"]
        health = client.get("/healthz").json()
        assert health["ok"] is True  # process is up; last_error carries the failure
        assert "认证失败" in health["last_error"]


def test_stream_mid_error_emits_sse_error_and_done(tmp_path):
    cfg = tmp_path / "gateway.json"
    cfg.write_text('{"backend":"mock"}', encoding="utf-8")
    app = create_app(config_path=cfg, config={"backend": "mock"}, load_env=False)
    app.state.gw.backend = FailingBackend({}, RuntimeError("Connection refused"), mid_stream=True)
    with TestClient(app) as client:
        r = client.post(
            "/v1/chat/completions",
            json={"stream": True, "messages": [{"role": "user", "content": "hi"}]},
        )
        assert r.status_code == 200
        assert "data: " in r.text
        assert "[DONE]" in r.text
        assert "无法连接" in r.text
        err_lines = [ln for ln in r.text.splitlines() if ln.startswith("data: ") and "error" in ln]
        assert err_lines
        payload = json.loads(err_lines[-1][6:])
        assert payload["error"]["code"] == 502


def test_validate_bind_host_rejects_wildcard_without_opt_in(monkeypatch):
    monkeypatch.delenv("AGENT_GATEWAY_ALLOW_LAN", raising=False)
    with pytest.raises(SystemExit, match="拒绝监听"):
        validate_bind_host("0.0.0.0")
    assert validate_bind_host("127.0.0.1") == "127.0.0.1"
    assert validate_bind_host("0.0.0.0", allow_lan=True) == "0.0.0.0"
