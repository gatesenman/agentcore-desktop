# Agent 网关（agent-service）

本机 OpenAI 兼容网关，默认监听 `127.0.0.1:18765`，把可插拔后端（mock / AgentScope / AgentCore / AG-UI / OpenAI 兼容）暴露给 ZCode 运行时。

## 运行（开发）

在 `agent-service/` 下：

```bash
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
# 可选：复制示例配置。不要提交 .env 或 gateway.json。
# cp gateway.example.json gateway.json
python run_gateway.py --host 127.0.0.1 --port 18765
```

健康检查：`curl -sS http://127.0.0.1:18765/healthz`

密钥请放在 `agent-service/.env` 或 `~/.agentcore-desktop/.env`，这两个路径都已被 gitignore。本仓库的 `gateway.example.json` 不含真实密钥。

## 测试

不需要任何云端 API Key（全部走 mock / 契约测试）：

```bash
cd agent-service
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
pytest -q
```

**未实测（缺凭证）：** `agentscope`、`agentcore`、真实 AG-UI / OpenAI 上游的端到端对话。相关后端代码在，但本测试套件不调用外部服务。

## 打包

`agent-gateway.spec` 供 PyInstaller 使用。切勿把 `.env` 打进包内。
