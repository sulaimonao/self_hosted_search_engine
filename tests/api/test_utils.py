from backend.app.api.utils import coerce_chat_identifier, sse_format


def test_coerce_chat_identifier_handles_nullish_values():
    assert coerce_chat_identifier(None) is None
    assert coerce_chat_identifier("") is None
    assert coerce_chat_identifier("  null  ") is None
    assert coerce_chat_identifier("undefined") is None


def test_coerce_chat_identifier_normalises_values():
    assert coerce_chat_identifier(" abc ") == "abc"
    assert coerce_chat_identifier(b"xyz") == "xyz"
    assert coerce_chat_identifier(123) == "123"


def test_sse_format_renders_event_frame():
    payload = sse_format('{"ok":true}', event="ping", retry=1000).decode()
    assert "retry: 1000" in payload
    assert "event: ping" in payload
    assert 'data: {"ok":true}' in payload
    assert payload.endswith("\n\n")


def test_sse_format_handles_empty_payload():
    payload = sse_format("", event=None, retry=None).decode()
    # for empty payload the SSE frame still contains a data line
    assert payload.startswith("data:\n")
    assert payload.endswith("\n\n")
