"""Normalization pipeline turning raw crawl results into search documents."""

from __future__ import annotations

import json
import logging
from collections import OrderedDict
from pathlib import Path
from typing import Dict, Iterable, Iterator, List

from bs4 import BeautifulSoup  # type: ignore[import-not-found]
from langdetect import DetectorFactory, LangDetectException, detect  # type: ignore[import-not-found]
from trafilatura import extract as trafilatura_extract  # type: ignore[import-not-found]

LOGGER = logging.getLogger(__name__)
DetectorFactory.seed = 42


def _read_raw_documents(raw_dir: Path) -> Iterator[Dict[str, object]]:
    for path in sorted(raw_dir.glob("*.jsonl")):
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                except json.JSONDecodeError:
                    LOGGER.debug("invalid json line in %s", path)
                    continue
                yield data


def _extract_text(html: str) -> str:
    if not html:
        return ""
    try:
        extracted = trafilatura_extract(html, include_comments=False, include_links=False)
    except Exception:
        extracted = None
    if extracted:
        return extracted.strip()
    soup = BeautifulSoup(html, "lxml")
    for element in soup.select("script, style, noscript"):
        element.decompose()
    text = " ".join(part.strip() for part in soup.get_text(" ").split())
    return text.strip()


def _collect_headings(html: str) -> str:
    if not html:
        return ""
    soup = BeautifulSoup(html, "lxml")
    headings: List[str] = []
    for tag in soup.find_all(["h1", "h2"]):
        text = tag.get_text(" ", strip=True)
        if text:
            headings.append(text)
    return " \n".join(headings)


def _detect_language(text: str) -> str:
    sample = text[:1000]
    if not sample.strip():
        return "unknown"
    try:
        return detect(sample)
    except LangDetectException:
        return "unknown"


def normalize(raw_dir: Path, output_path: Path) -> List[Dict[str, str]]:
    """Normalize raw crawl documents into JSONL output.

    Returns the list of normalized documents written to ``output_path``.
    """

    docs: "OrderedDict[str, Dict[str, str]]" = OrderedDict()
    for record in _read_raw_documents(raw_dir):
        url = str(record.get("url") or "").strip()
        status = int(record.get("status") or 0)
        if not url or status >= 400:
            continue
        html = str(record.get("html") or "")
        title = str(record.get("title") or "")
        body = _extract_text(html)
        if not body:
            continue
        headings = _collect_headings(html)
        lang = _detect_language(body)
        docs[url] = {
            "url": url,
            "title": title,
            "h1h2": headings,
            "body": body,
            "lang": lang,
        }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as handle:
        for doc in docs.values():
            handle.write(json.dumps(doc, ensure_ascii=False) + "\n")
    LOGGER.info("normalized %s document(s) into %s", len(docs), output_path)
    return list(docs.values())
