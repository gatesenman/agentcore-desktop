"""SiliconFlow / Qwen tool-call template fragments must not leak into content."""
from agent_gateway.backends.openai_compat import _clean, _ContentFilter


def test_clean_strips_closed_tool_call_tags():
    leaked = 'hello}\n</tool_call> world'
    assert "</tool_call>" not in _clean(leaked)
    assert "hello" in _clean(leaked)
    assert "world" in _clean(leaked)


def test_content_filter_holds_partial_tag_then_flushes_clean_text():
    flt = _ContentFilter()
    # first chunk ends mid-tag; should not emit the partial marker
    out1 = flt.feed("answer}\n</tool_ca")
    assert "</tool" not in out1
    out2 = flt.feed("ll>\nvisible")
    flushed = out2 + flt.flush()
    combined = out1 + flushed
    assert "visible" in combined
    assert "tool_call" not in combined
