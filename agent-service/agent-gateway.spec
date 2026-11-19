# -*- mode: python ; coding: utf-8 -*-
# 跨平台 PyInstaller spec（Linux / Windows / macOS 通用）。用法：pyinstaller -y agent-gateway.spec
# 产物：dist/agent-gateway/agent-gateway(.exe)。切勿把 .env 打进包内（此处未收集）。
from PyInstaller.utils.hooks import collect_all, collect_submodules

datas, binaries, hiddenimports = [], [], []
for pkg in ("agentscope", "agentcore"):
    d, b, h = collect_all(pkg)
    datas += d; binaries += b; hiddenimports += h
hiddenimports += collect_submodules("agent_gateway")
hiddenimports += ["uvicorn.logging", "uvicorn.loops.auto", "uvicorn.protocols.http.auto",
                  "uvicorn.protocols.websockets.auto", "uvicorn.lifespan.on"]

a = Analysis(["run_gateway.py"], pathex=["."], binaries=binaries, datas=datas, hiddenimports=hiddenimports,
             excludes=["tkinter"], noarchive=False)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="agent-gateway", console=True,
          upx=False, icon=None)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="agent-gateway")
