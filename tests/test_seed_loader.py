from seed_loader.curate import curate_seeds
from seed_loader.sources import SeedSource


def test_curate_seeds_respects_quotas():
    sources = [
        SeedSource(url="https://example.com/docs", source="list", tags={"list"}),
        SeedSource(url="https://docs.example.org", source="list", tags={"list"}),
        SeedSource(url="https://service.fr/guide", source="list", tags={"list"}),
        SeedSource(url="https://portal.de/help", source="list", tags={"list"}),
        SeedSource(url="https://docs.example.mx", source="list", tags={"list"}),
        SeedSource(url="https://example.jp/docs", source="list", tags={"list"}),
        SeedSource(url="https://example.com/blog", source="list", tags={"list"}),
        SeedSource(url="https://example.co.uk/guide", source="list", tags={"list"}),
        SeedSource(url="https://example.in/docs", source="list", tags={"list"}),
        SeedSource(url="https://example.ca/docs", source="list", tags={"list"}),
    ]

    curated = curate_seeds(sources, limit=8, non_en_quota=0.4, non_us_quota=0.5)
    assert curated
    assert len(curated) <= 8
    urls = {candidate.url for candidate in curated}
    assert len(urls) == len(curated), "expected deduplicated URLs"

    non_en = sum(1 for candidate in curated if candidate.lang != "en")
    non_us = sum(1 for candidate in curated if candidate.region != "us")

    assert non_en / len(curated) >= 0.4
    assert non_us / len(curated) >= 0.5
