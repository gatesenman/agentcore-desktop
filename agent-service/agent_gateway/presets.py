"""Backend labels and key-free configuration presets for the settings UI."""
from __future__ import annotations

from .backends import REGISTRY

BACKEND_LABELS = {
    "mock": "本地模拟（无需密钥，适合离线试用）",
    "agentscope": "AgentScope（DashScope / 兼容 OpenAI 的模型）",
    "openai": "OpenAI 兼容（硅基流动、vLLM、自建网关等）",
    "agui": "AG-UI 协议客户端",
    "agentcore": "阿里云 AgentCore 托管模型",
}

PRESETS = {
    "mock": {
        "backend": "mock",
        "label": "本地模拟",
        "description": "不调用外部服务，原样回显用户输入。无需 API Key。",
        "config": {},
        "env_keys": [],
    },
    "siliconflow": {
        "backend": "openai",
        "label": "硅基流动（OpenAI 兼容）",
        "description": "将密钥写入 .env 的 SILICONFLOW_API_KEY，不要写进 gateway.json。",
        "config": {
            "base_url": "https://api.siliconflow.cn/v1",
            "upstream_model": "Qwen/Qwen2.5-7B-Instruct",
        },
        "env_keys": ["SILICONFLOW_API_KEY", "SILICONFLOW_MODEL"],
    },
    "dashscope": {
        "backend": "agentscope",
        "label": "阿里云百炼 / DashScope",
        "description": "将密钥写入 .env 的 DASHSCOPE_API_KEY。",
        "config": {"model_provider": "dashscope", "model": "qwen-plus"},
        "env_keys": ["DASHSCOPE_API_KEY"],
    },
    "openai-compat": {
        "backend": "openai",
        "label": "通用 OpenAI 兼容端点",
        "description": "自定义 base_url；密钥用 OPENAI_COMPAT_API_KEY。",
        "config": {"base_url": "http://127.0.0.1:8000/v1", "upstream_model": ""},
        "env_keys": ["OPENAI_COMPAT_API_KEY", "OPENAI_COMPAT_BASE_URL", "OPENAI_COMPAT_MODEL"],
    },
    "agentcore": {
        "backend": "agentcore",
        "label": "阿里云 AgentCore",
        "description": "需要模型资源名与阿里云凭证，均放在 .env，勿提交。",
        "config": {},
        "env_keys": [
            "AGENTCORE_MODEL_RESOURCE",
            "AGENTCORE_MODEL",
            "ALIBABA_CLOUD_ACCESS_KEY_ID",
            "ALIBABA_CLOUD_ACCESS_KEY_SECRET",
        ],
    },
    "agui": {
        "backend": "agui",
        "label": "AG-UI",
        "description": "连接到讲 AG-UI 协议的 Agent 服务。端到端需真实服务，本仓库仅提供契约。",
        "config": {},
        "env_keys": [],
    },
}


def list_presets() -> dict:
    available = set(REGISTRY)
    presets = []
    for key, spec in PRESETS.items():
        presets.append({
            "id": key,
            "backend": spec["backend"],
            "label": spec["label"],
            "description": spec["description"],
            "config": spec["config"],
            "env_keys": spec["env_keys"],
            "backend_available": spec["backend"] in available,
        })
    backends = [
        {"id": name, "label": BACKEND_LABELS.get(name, name), "available": True}
        for name in sorted(available)
    ]
    return {"presets": presets, "backends": backends}
