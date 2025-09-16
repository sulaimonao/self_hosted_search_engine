from crawler.frontier import FrontierDB


def test_frontier_enqueue_and_cap(tmp_path):
    db_path = tmp_path / "frontier.sqlite"
    frontier = FrontierDB(db_path, per_domain_cap=2, max_total=10)
    try:
        assert frontier.enqueue("https://example.com/", depth=0) == 1
        assert frontier.enqueue("https://example.com/", depth=0) == 0
        assert frontier.enqueue("https://example.com/about", depth=1) == 1
        # Exceed per-domain cap
        assert frontier.enqueue("https://example.com/contact", depth=1) == 0
        entries = list(frontier.next_entries(10))
        assert len(entries) == 2
        for entry in entries:
            frontier.mark_fetched(entry.url)
        stats = frontier.stats()
        assert stats["fetched"] == 2
    finally:
        frontier.close()
