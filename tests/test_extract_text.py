from crawler.utils import extract_text


def test_extract_text_removes_scripts_and_whitespace():
    html = """
    <html><head><title>Test</title><script>var x=1;</script></head>
    <body>
      <h1>Heading</h1>
      <p>First paragraph.</p>
      <div>Second <strong>paragraph</strong>.</div>
    </body></html>
    """
    text = extract_text(html)
    assert "Heading" in text
    assert "First paragraph." in text
    assert "Second" in text
    assert "var x" not in text
