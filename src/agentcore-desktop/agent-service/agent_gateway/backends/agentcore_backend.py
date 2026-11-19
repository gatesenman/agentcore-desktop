"""Alibaba Cloud AgentCore backend: AgentScope agent whose model is an AgentCore *managed model resource*
(resolved by alibabacloud-agentcore-sdk). Needs credentials — see README「AgentCore 配置」.

Env / gateway.json(backends.agentcore):
  AGENTCORE_MODEL_RESOURCE  (required) model resource name in the AgentCore workspace
  AGENTCORE_MODEL           (optional) specific model under that resource
  AGENTCORE_DEBUG_TOKEN     local-dev token from the AgentCore console  — or —
  AGENTCORE_CONFIG_PATH / AGENTCORE_ENV_PATH  runtime config files
  ALIBABA_CLOUD_ACCESS_KEY_ID / ALIBABA_CLOUD_ACCESS_KEY_SECRET (/ ALIBABA_CLOUD_SECURITY_TOKEN)
  AGENTCORE_CONTROL_PLANE_ENDPOINT (optional)
"""
import asyncio
import os
from .agentscope_backend import AgentScopeBackend


class AgentCoreBackend(AgentScopeBackend):
    name = "agentcore"
    _cached = None

    def _model(self):
        if self._cached is not None:
            return self._cached
        from agentcore.auth import AccessKeyCredential
        from agentcore.integrations import agentscope as ac
        c, e = self.config, os.environ
        resource = c.get("model_resource") or e.get("AGENTCORE_MODEL_RESOURCE")
        if not resource:
            raise RuntimeError("AgentCore backend: set AGENTCORE_MODEL_RESOURCE (and credentials)")
        ak = c.get("access_key_id") or e.get("ALIBABA_CLOUD_ACCESS_KEY_ID")
        sk = c.get("access_key_secret") or e.get("ALIBABA_CLOUD_ACCESS_KEY_SECRET")
        if c.get("debug_token"):
            os.environ["AGENTCORE_DEBUG_TOKEN"] = c["debug_token"]
        cred = AccessKeyCredential(ak, sk, e.get("ALIBABA_CLOUD_SECURITY_TOKEN") or None) if ak and sk else None
        self._cached = ac.model(
            resource,
            model_name=c.get("model") or e.get("AGENTCORE_MODEL") or None,
            config_path=c.get("config_path") or e.get("AGENTCORE_CONFIG_PATH") or None,
            env_path=c.get("env_path") or e.get("AGENTCORE_ENV_PATH") or None,
            control_plane_endpoint=c.get("control_plane_endpoint") or e.get("AGENTCORE_CONTROL_PLANE_ENDPOINT") or None,
            access_key_credential=cred,
        )
        return self._cached

    async def chat(self, body):
        # SDK resolves synchronously via its own blocking portal; resolve off the event loop first.
        await asyncio.to_thread(self._model)
        async for d in super().chat(body):
            yield d
