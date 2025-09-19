"""Whoosh schema definition with field boosts."""

from __future__ import annotations

from whoosh.fields import ID, TEXT, Schema
from whoosh.analysis import StemmingAnalyzer


def build_schema() -> Schema:
    analyzer = StemmingAnalyzer()
    return Schema(
        url=ID(stored=True, unique=True),
        lang=ID(stored=True),
        title=TEXT(stored=True, field_boost=4.0, analyzer=analyzer, phrase=True),
        h1h2=TEXT(stored=True, field_boost=2.0, analyzer=analyzer, phrase=True),
        body=TEXT(stored=True, analyzer=analyzer, phrase=True),
    )
