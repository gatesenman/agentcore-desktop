"""Gateway contract tests: no real API keys, no user ~/.agentcore-desktop/.env."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@pytest.fixture()
def gateway_app(tmp_path, monkeypatch):
    # Isolate from the developer's machine env and data dir.
    monkeypatch.delenv("AGENT_GATEWAY_CONFIG", raising=False)
    monkeypatch.delenv("AGENT_BACKEND", raising=False)
    monkeypatch.delenv("AGENT_GATEWAY_ENV_DIR", raising=False)
    monkeypatch.delenv("AGENT_GATEWAY_DUMP", raising=False)
    monkeypatch.delenv("AGENT_GATEWAY_TOOLLOG", raising=False)
    # Do not inherit cloud keys into auto-backend selection during tests.
    for key in (
        "DASHSCOPE_API_KEY",
        "SILICONFLOW_API_KEY",
        "OPENAI_COMPAT_API_KEY",
        "OPENAI_API_KEY",
    ):
        monkeypatch.delenv(key, raising=False)

    cfg_path = tmp_path / "gateway.json"
    cfg_path.write_text('{"backend": "mock"}', encoding="utf-8")
    from agent_gateway.server import create_app

    return create_app(config_path=cfg_path, config={"backend": "mock"}, load_env=False)
