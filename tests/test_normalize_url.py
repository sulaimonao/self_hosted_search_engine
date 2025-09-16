from crawler.utils import normalize_url


def test_normalize_url_basic():
    assert normalize_url("HTTP://Example.COM/About") == "http://example.com/About"


def test_normalize_url_fragment_and_query():
    url = "https://example.com/path/../page/?b=2&a=1#section"
    assert normalize_url(url) == "https://example.com/page/?a=1&b=2"


def test_normalize_url_default_port_removed():
    assert normalize_url("https://example.com:443/") == "https://example.com/"
