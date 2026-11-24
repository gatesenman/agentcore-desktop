from fastapi.testclient import TestClient

from agent_gateway.presets import PRESETS, list_presets


def test_presets_have_no_secret_values():
    dumped = str(list_presets())
    assert "sk-" not in dumped
    for spec in PRESETS.values():
        for key in ("api_key", "token", "access_key_id", "access_key_secret", "debug_token"):
            assert key not in spec["config"]


def test_admin_presets_and_labels(gateway_app):
    with TestClient(gateway_app) as client:
        r = client.get("/admin/presets")
        assert r.status_code == 200
        body = r.json()
        ids = {p["id"] for p in body["presets"]}
        assert {"mock", "siliconflow", "dashscope", "agentcore", "agui"} <= ids
        assert any("硅基流动" in p["label"] for p in body["presets"])
        backend = client.get("/admin/backend").json()
        assert "backend_label" in backend
        assert "本地模拟" in backend["backend_label"]
        page = client.get("/settings").text
        assert "快捷预设" in page
        assert "不要填写 api_key" in page
