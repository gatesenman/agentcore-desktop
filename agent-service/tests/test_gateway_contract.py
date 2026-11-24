"""Mock / contract tests for the Agent Gateway. No upstream API keys required."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from agent_gateway.server import create_app, load_config


def test_healthz_reports_mock_backend(gateway_app):
    with TestClient(gateway_app) as client:
        r = client.get("/healthz")
        assert r.status_code == 200
        body = r.json()
        assert body["ok"] is True
        assert body["backend"] == "mock"
        assert "uptime_s" in body
        assert body["last_error"] is None


def test_models_lists_gateway_model(gateway_app):
    with TestClient(gateway_app) as client:
        r = client.get("/v1/models")
        assert r.status_code == 200
        ids = [m["id"] for m in r.json()["data"]]
        assert "mock" in ids or "agent-gateway" in ids


def test_chat_completions_non_stream_echoes_user_text(gateway_app):
    with TestClient(gateway_app) as client:
        r = client.post(
            "/v1/chat/completions",
            json={"model": "agent-gateway", "stream": False, "messages": [{"role": "user", "content": "你好"}]},
        )
        assert r.status_code == 200
        msg = r.json()["choices"][0]["message"]["content"]
        assert "[mock agent]" in msg
        assert "你好" in msg
        assert r.json()["choices"][0]["finish_reason"] == "stop"


def test_chat_completions_stream_emits_sse_and_done(gateway_app):
    with TestClient(gateway_app) as client:
        r = client.post(
            "/v1/chat/completions",
            json={"model": "agent-gateway", "stream": True, "messages": [{"role": "user", "content": "ping"}]},
        )
        assert r.status_code == 200
        assert "text/event-stream" in r.headers["content-type"]
        raw = r.text
        assert "data: " in raw
        assert "[DONE]" in raw
        pieces = []
        for line in raw.splitlines():
            if not line.startswith("data: ") or line.strip() == "data: [DONE]":
                continue
            obj = json.loads(line[6:])
            delta = (obj.get("choices") or [{}])[0].get("delta") or {}
            if delta.get("content"):
                pieces.append(delta["content"])
        assembled = "".join(pieces)
        assert "ping" in assembled
        assert "[mock agent]" in assembled


def test_admin_rejects_non_json_content_type(gateway_app):
    with TestClient(gateway_app) as client:
        r = client.post(
            "/admin/backend",
            content='{"backend":"mock"}',
            headers={"content-type": "text/plain"},
        )
        assert r.status_code == 415


def test_admin_unknown_backend_is_400(gateway_app):
    with TestClient(gateway_app) as client:
        r = client.post("/admin/backend", json={"backend": "does-not-exist", "config": {}})
        assert r.status_code == 400
        assert "未知后端" in r.json()["error"]


def test_admin_get_does_not_echo_secrets(tmp_path):
    cfg_path = tmp_path / "gateway.json"
    cfg_path.write_text(
        json.dumps(
            {
                "backend": "mock",
                "backends": {"mock": {"api_key": "sk-SHOULD-NOT-APPEAR", "sys_prompt": "hi"}},
            }
        ),
        encoding="utf-8",
    )
    app = create_app(
        config_path=cfg_path,
        config={"backend": "mock", "api_key": "sk-SHOULD-NOT-APPEAR", "sys_prompt": "hi"},
        load_env=False,
    )
    with TestClient(app) as client:
        r = client.get("/admin/backend")
        assert r.status_code == 200
        body = r.json()
        dumped = json.dumps(body)
        assert "sk-SHOULD-NOT-APPEAR" not in dumped
        assert "api_key" not in body.get("config", {})
        assert "api_key" in body["secrets_set"]
        assert body["config"].get("sys_prompt") == "hi"


def test_load_config_unknown_backend_is_value_error(tmp_path):
    path = tmp_path / "gateway.json"
    path.write_text('{"backend": "not-a-backend"}', encoding="utf-8")
    with pytest.raises(ValueError, match="未知后端"):
        load_config(path, environ={})


def test_load_config_defaults_to_mock_without_keys(tmp_path):
    path = tmp_path / "missing.json"
    cfg = load_config(path, environ={})
    assert cfg["backend"] == "mock"


def test_local_cloud_stub_is_offline_404(gateway_app):
    with TestClient(gateway_app) as client:
        r = client.get("/some/zhipu/cloud/path")
        assert r.status_code == 404
        assert r.json()["msg"] == "disabled in AgentCore Desktop (offline)"


def test_settings_page_is_chinese(gateway_app):
    with TestClient(gateway_app) as client:
        r = client.get("/settings")
        assert r.status_code == 200
        assert "Agent 后端设置" in r.text


def test_gitignore_excludes_secrets():
    root = Path(__file__).resolve().parents[2]
    ignore = (root / ".gitignore").read_text(encoding="utf-8")
    local = (root / "agent-service" / ".gitignore").read_text(encoding="utf-8")
    combined = ignore + "\n" + local
    assert "agent-service/.env" in ignore or ".env" in local
    assert "gateway.json" in combined
