"""Frozen entrypoint (PyInstaller). Usage: agent-gateway [--port N]  (env: AGENT_BACKEND, AGENT_GATEWAY_CONFIG, .env next to binary or in AGENT_GATEWAY_ENV_DIR)"""
import argparse
import os
import sys
from pathlib import Path

if getattr(sys, "frozen", False):
    os.environ.setdefault("AGENT_GATEWAY_ENV_DIR", str(Path(sys.executable).parent))

import uvicorn
from agent_gateway.server import app


def validate_bind_host(host: str, allow_lan: bool | None = None) -> str:
    """Default to loopback-only. Binding 0.0.0.0 requires an explicit opt-in."""
    if allow_lan is None:
        allow_lan = os.environ.get("AGENT_GATEWAY_ALLOW_LAN") == "1"
    normalized = (host or "").strip().lower()
    if normalized in {"0.0.0.0", "::", "[::]"} and not allow_lan:
        raise SystemExit(
            "拒绝监听所有网卡。网关只应绑定 127.0.0.1。"
            "若确需局域网访问，请设置 AGENT_GATEWAY_ALLOW_LAN=1。"
        )
    return host


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=int(os.environ.get("AGENT_GATEWAY_PORT", 18765)))
    a = ap.parse_args()
    host = validate_bind_host(a.host)
    uvicorn.run(app, host=host, port=a.port, log_level="warning")
