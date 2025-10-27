import sqlite3

from backend.tools.termsearch.core import search_docs


def test_search_handles_apostrophes(tmp_path):
    db_path = tmp_path / "docs.sqlite3"
    connection = sqlite3.connect(db_path)
    try:
        connection.execute("CREATE VIRTUAL TABLE docs_fts USING fts5(url, title, body)")
        connection.execute(
            "INSERT INTO docs_fts(url, title, body) VALUES (?, ?, ?)",
            (
                "https://example.com/today",
                "Today's News",
                "Today's news explains the latest events.",
            ),
        )
        connection.commit()
    finally:
        connection.close()

    results = search_docs(db_path, "today's news")
    assert len(results) == 1
    assert results[0]["url"] == "https://example.com/today"
