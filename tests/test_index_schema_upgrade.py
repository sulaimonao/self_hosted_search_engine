from whoosh import index
from whoosh.fields import ID, TEXT, Schema

from backend.app.indexer.incremental import ensure_index, REQUIRED_FIELDS
from backend.app.indexer.schema import build_schema


def test_ensure_index_upgrades_legacy_schema(tmp_path):
    index_dir = tmp_path / "legacy_index"
    index_dir.mkdir()

    legacy_schema = Schema(
        url=ID(stored=True, unique=True),
        title=TEXT(stored=True),
        text=TEXT(stored=True),
    )
    legacy_ix = index.create_in(index_dir, legacy_schema)
    writer = legacy_ix.writer()
    writer.commit()
    legacy_ix.close()

    upgraded_ix = ensure_index(index_dir)
    try:
        names = set(upgraded_ix.schema.names())
        assert REQUIRED_FIELDS.issubset(names)

        desired_schema = build_schema()
        for field_name in REQUIRED_FIELDS:
            upgraded_field = upgraded_ix.schema[field_name]
            desired_field = desired_schema[field_name]
            assert upgraded_field.__class__ is desired_field.__class__
            assert bool(getattr(upgraded_field, "stored", False)) == bool(
                getattr(desired_field, "stored", False)
            )
            assert getattr(upgraded_field, "field_boost", 1.0) == getattr(
                desired_field, "field_boost", 1.0
            )
            upgraded_analyzer = getattr(upgraded_field, "analyzer", None)
            desired_analyzer = getattr(desired_field, "analyzer", None)
            assert (
                upgraded_analyzer.__class__ if upgraded_analyzer is not None else None
            ) is (
                desired_analyzer.__class__ if desired_analyzer is not None else None
            )

        writer = upgraded_ix.writer()
        writer.add_document(
            url="https://example.com/",
            lang="en",
            title="Example Title",
            h1h2="Example Heading",
            body="Body text for schema upgrade test.",
        )
        writer.commit()
    finally:
        upgraded_ix.close()


def test_ensure_index_recovers_from_missing_segment(tmp_path):
    index_dir = tmp_path / "corrupt_index"
    ix = ensure_index(index_dir)
    writer = ix.writer()
    writer.add_document(
        url="https://example.com/",
        lang="en",
        title="Example",
        h1h2="Example",
        body="Example body",
    )
    writer.commit()
    ix.close()

    segments = list(index_dir.glob("MAIN_*.seg"))
    assert segments, "Expected at least one Whoosh segment file"
    for segment in segments:
        segment.unlink()

    recovered = ensure_index(index_dir)
    try:
        with recovered.searcher() as searcher:
            assert searcher.doc_count_all() == 0
    finally:
        recovered.close()
