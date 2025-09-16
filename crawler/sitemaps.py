from __future__ import annotations

from collections import deque
from typing import Iterable, List, Set
from urllib.parse import urlparse

import requests
from requests.exceptions import RequestException

from crawler.utils import normalize_url


def fetch_sitemap(url: str, user_agent: str, timeout: int = 15) -> str | None:
    headers = {"User-Agent": user_agent}
    try:
        response = requests.get(url, headers=headers, timeout=timeout)
        if response.status_code != 200:
            return None
        return response.text
    except RequestException:
        return None


def parse_sitemap(xml_text: str) -> List[str]:
    import xml.etree.ElementTree as ET

    urls: List[str] = []
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return urls
    ns = "{http://www.sitemaps.org/schemas/sitemap/0.9}"
    if root.tag.endswith("sitemapindex"):
        for child in root.findall(f"{ns}sitemap/{ns}loc"):
            if child.text:
                urls.append(child.text.strip())
    elif root.tag.endswith("urlset"):
        for child in root.findall(f"{ns}url/{ns}loc"):
            if child.text:
                urls.append(child.text.strip())
    return urls


def collect_sitemap_urls(start_urls: Iterable[str], user_agent: str, per_domain_cap: int) -> List[str]:
    discovered: List[str] = []
    seen: Set[str] = set()
    queue: deque[str] = deque(start_urls)
    while queue:
        sitemap_url = queue.popleft()
        if sitemap_url in seen:
            continue
        seen.add(sitemap_url)
        xml_text = fetch_sitemap(sitemap_url, user_agent=user_agent)
        if not xml_text:
            continue
        for url in parse_sitemap(xml_text):
            if url.lower().endswith(".xml"):
                queue.append(url)
            else:
                discovered.append(normalize_url(url))
    if per_domain_cap:
        counts: dict[str, int] = {}
        limited: List[str] = []
        for url in discovered:
            domain = urlparse(url).netloc
            if counts.get(domain, 0) >= per_domain_cap:
                continue
            counts[domain] = counts.get(domain, 0) + 1
            limited.append(url)
        return limited
    return discovered
