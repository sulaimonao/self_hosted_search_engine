from whoosh import index
from whoosh.fields import ID, TEXT, Schema

from backend.app.indexer.incremental import ensure_index, REQUIRED_FIELDS


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
