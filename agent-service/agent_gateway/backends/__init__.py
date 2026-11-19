"""Backend registry. To add a framework: implement AgentBackend and register it here."""
from .mock import MockBackend
from .openai_compat import OpenAICompatBackend
from .agentscope_backend import AgentScopeBackend
from .agui import AGUIBackend
from .agentcore_backend import AgentCoreBackend

REGISTRY = {b.name: b for b in (MockBackend, OpenAICompatBackend, AgentScopeBackend, AGUIBackend, AgentCoreBackend)}
