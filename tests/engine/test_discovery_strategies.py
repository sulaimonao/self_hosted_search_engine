from unittest.mock import patch

from engine.discovery.strategies import external_search_strategy


@patch("engine.discovery.utils.google_search")
def test_external_search_strategy(mock_google_search):
    mock_google_search.return_value = [
        {"link": "https://example.com/1", "title": "Title 1", "snippet": "Snippet 1"},
        {"link": "https://example.com/2", "title": "Title 2", "snippet": "Snippet 2"},
    ]

    candidates = external_search_strategy("test query")

    assert len(candidates) == 2
    assert candidates[0].url == "https://example.com/1"
    assert candidates[0].title == "Title 1"
    assert candidates[0].summary == "Snippet 1"
    assert candidates[1].url == "https://example.com/2"
    assert candidates[1].title == "Title 2"
    assert candidates[1].summary == "Snippet 2"

    mock_google_search.assert_called_once_with("test query", limit=10)
