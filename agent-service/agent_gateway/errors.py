"""面向用户的上游错误映射。不记录、不回传密钥原文。"""
from __future__ import annotations

import re

_SECRET = re.compile(
    r"(?i)(sk-[A-Za-z0-9]{8,}|Bearer\s+\S+|api[_-]?key\s*[=:]\s*\S+)",
)

STATUS_ZH = {
    401: "上游认证失败，请检查 API Key 是否有效。",
    403: "上游拒绝访问，请检查权限或额度。",
    404: "上游接口不存在，请检查模型服务地址。",
    408: "上游请求超时，请稍后重试。",
    429: "上游请求过于频繁，请稍后再试。",
    500: "上游服务内部错误。",
    502: "无法连接到上游模型服务。",
    503: "上游服务暂时不可用。",
    504: "上游网关超时，请稍后重试。",
}

CONN_MARKERS = (
    "connecterror",
    "connection refused",
    "connection reset",
    "name or service not known",
    "nodename nor servname",
    "temporary failure in name resolution",
    "network is unreachable",
    "timed out",
    "timeout",
)


def sanitize_error_text(text: str, limit: int = 500) -> str:
    cleaned = _SECRET.sub("<redacted>", text or "")
    return cleaned[:limit]


def public_error(exc: BaseException) -> tuple[int, str]:
    """Return (http_status, chinese_or_sanitized_message)."""
    status = getattr(exc, "status", None) or getattr(exc, "status_code", None)
    if not isinstance(status, int) or not (400 <= status < 600):
        status = None
    raw = sanitize_error_text(str(exc))
    if status in STATUS_ZH:
        return status, STATUS_ZH[status]
    lowered = raw.lower()
    if any(m in lowered for m in CONN_MARKERS):
        return 502, STATUS_ZH[502]
    if status is None:
        status = 502
    # 未知状态仍给中文框架，避免把上游原文（可能含内部路径）直接甩给 UI。
    return status, f"上游服务返回错误（HTTP {status}）。"
