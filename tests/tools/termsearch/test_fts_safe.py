from backend.tools.termsearch.core import _fts_safe


def test_fts_safe_quotes_tokens():
    assert _fts_safe("today's news") == "\"today's\" \"news\""
    assert _fts_safe("  multiple   spaces  ") == "\"multiple\" \"spaces\""
    assert _fts_safe("") == ""
    assert _fts_safe("He said \"hello\"") == "\"He\" \"said\" \"\"\"hello\"\"\""
