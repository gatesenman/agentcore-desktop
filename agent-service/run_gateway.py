"""Frozen entrypoint (PyInstaller). Usage: agent-gateway [--port N]  (env: AGENT_BACKEND, AGENT_GATEWAY_CONFIG, .env next to binary or in AGENT_GATEWAY_ENV_DIR)"""
import argparse, os, sys
from pathlib import Path

if getattr(sys, "frozen", False):
    os.environ.setdefault("AGENT_GATEWAY_ENV_DIR", str(Path(sys.executable).parent))

import uvicorn
from agent_gateway.server import app

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=int(os.environ.get("AGENT_GATEWAY_PORT", 18765)))
    a = ap.parse_args()
    uvicorn.run(app, host=a.host, port=a.port, log_level="warning")
