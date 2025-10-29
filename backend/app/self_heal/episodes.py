from __future__ import annotations

import json
import os
import time
import uuid
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

EPISODES_DIR = Path(os.getenv("SELF_HEAL_EPISODES_DIR", "data/self_heal/episodes"))


@dataclass
class Episode:
    id: str
    ts: int
    url: str
    symptoms: Dict[str, Any]
    directive: Dict[str, Any]
    mode: str
    outcome: str
    details: Dict[str, Any]
    meta: Dict[str, Any]


def _month_slug(ts: Optional[int] = None) -> str:
    t = time.gmtime(ts or time.time())
    return f"{t.tm_year:04d}{t.tm_mon:02d}"


def _ensure_month_file(base: Path, month: Optional[str] = None) -> Path:
    month = month or _month_slug()
    month_dir = base / month
    month_dir.mkdir(parents=True, exist_ok=True)
    return month_dir / "episodes.jsonl"


def append_episode(
    *,
    url: str,
    symptoms: Dict[str, Any],
    directive: Dict[str, Any],
    mode: str,
    outcome: str = "unknown",
    details: Optional[Dict[str, Any]] = None,
    meta: Optional[Dict[str, Any]] = None,
    ts: Optional[int] = None,
    episodes_dir: Path = EPISODES_DIR,
) -> Tuple[str, Path]:
    episode = Episode(
        id=str(uuid.uuid4()),
        ts=int(ts or time.time()),
        url=str(url or ""),
        symptoms=dict(symptoms or {}),
        directive=dict(directive or {}),
        mode=str(mode or "plan"),
        outcome=str(outcome or "unknown"),
        details=dict(details or {}),
        meta=dict(meta or {}),
    )
    file_path = _ensure_month_file(episodes_dir, _month_slug(episode.ts))
    with file_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(asdict(episode), ensure_ascii=False) + "\n")
    return episode.id, file_path


def iter_episodes(
    *,
    episodes_dir: Path = EPISODES_DIR,
    month: Optional[str] = None,
    limit: Optional[int] = 200,
    reverse: bool = True,
) -> Iterable[Dict[str, Any]]:
    base = episodes_dir
    if not base.exists():
        return []
    months: List[str]
    if month:
        months = [month]
    else:
        months = sorted([p.name for p in base.iterdir() if p.is_dir()], reverse=True)
    count = 0
    for slug in months:
        path = base / slug / "episodes.jsonl"
        if not path.exists():
            continue
        with path.open("r", encoding="utf-8") as handle:
            lines = handle.readlines()
        if reverse:
            lines = list(reversed(lines))
        for line in lines:
            payload = line.strip()
            if not payload:
                continue
            try:
                data = json.loads(payload)
            except Exception:
                continue
            yield data
            count += 1
            if limit and count >= limit:
                return


def get_episode_by_id(ep_id: str, *, episodes_dir: Path = EPISODES_DIR) -> Optional[Dict[str, Any]]:
    for item in iter_episodes(episodes_dir=episodes_dir, limit=None, reverse=True):
        if item.get("id") == ep_id:
            return item
    return None


__all__ = [
    "EPISODES_DIR",
    "Episode",
    "append_episode",
    "iter_episodes",
    "get_episode_by_id",
]
