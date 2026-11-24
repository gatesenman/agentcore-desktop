from agent_gateway.errors import public_error, sanitize_error_text
from agent_gateway.backends.base import UpstreamError


def test_known_status_uses_chinese_message():
    status, message = public_error(UpstreamError(401, "invalid api key sk-LEAKEDSECRETVALUE"))
    assert status == 401
    assert "认证失败" in message
    assert "sk-LEAKEDSECRETVALUE" not in message


def test_rate_limit_and_connection_messages():
    status, message = public_error(UpstreamError(429, "too many requests"))
    assert status == 429
    assert "过于频繁" in message
    status, message = public_error(ConnectionError("Connection refused"))
    assert status == 502
    assert "无法连接" in message


def test_sanitize_redacts_bearer_and_keys():
    text = sanitize_error_text("Authorization: Bearer abcdefghijklmnop body")
    assert "abcdefghijklmnop" not in text
    assert "<redacted>" in text
