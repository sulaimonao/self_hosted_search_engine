"""Search package exposing index helpers."""

from .indexer import create_or_open_index, index_documents
from .query import search

__all__ = ["create_or_open_index", "index_documents", "search"]
