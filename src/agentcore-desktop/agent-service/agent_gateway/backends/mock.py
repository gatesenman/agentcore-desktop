import asyncio
from .base import AgentBackend, text_of


class MockBackend(AgentBackend):
    """Offline echo model, used when no API key is configured."""
    name = "mock"

    async def stream(self, messages, model):
        last = next((text_of(m.get("content")) for m in reversed(messages) if m.get("role") == "user"), "")
        reply = f"[mock agent] 收到：{last.strip()[-500:]}"
        for i in range(0, len(reply), 8):
            await asyncio.sleep(0.01)
            yield reply[i : i + 8]
