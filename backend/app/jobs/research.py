"""Deep research orchestration using Ollama and the focused crawl pipeline."""

from __future__ import annotations

import json
import re
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests

from ..config import AppConfig
def _ollama_request(url: str, model: Optional[str], system: str, prompt: str) -> str:
    payload = {
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
        "stream": False,
    }
    if model:
        payload["model"] = model
    try:
        response = requests.post(f"{url}/api/chat", json=payload, timeout=180)
    except requests.RequestException as exc:
        return json.dumps({"error": str(exc)})
    if response.status_code >= 400:
        return json.dumps({"error": response.text.strip() or response.status_code})
    try:
        data = response.json()
    except ValueError:
        return response.text
    message = data.get("message", {})
    return message.get("content", "")


def _parse_plan(text: str) -> Dict[str, Any]:
    if not text:
        return {"tasks": [], "sources": []}
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            tasks = parsed.get("tasks") or parsed.get("plan") or []
            sources = parsed.get("sources") or parsed.get("urls") or []
            if isinstance(tasks, list) and isinstance(sources, list):
                return {"tasks": tasks, "sources": sources}
    except ValueError:
        pass
    urls = re.findall(r"https?://\S+", text)
    bullets = [line.strip(" -*") for line in text.splitlines() if line.strip()]
    return {"tasks": bullets[:5], "sources": urls[:10]}


def _trim_document(doc: Dict[str, Any], limit: int = 1200) -> Dict[str, Any]:
    body = doc.get("body", "")
    snippet = body[:limit]
    return {
        "url": doc.get("url", ""),
        "title": doc.get("title", ""),
        "body": snippet,
        "lang": doc.get("lang", "unknown"),
    }


def _write_report(report_dir: Path, content: str) -> Path:
    report_dir.mkdir(parents=True, exist_ok=True)
    path = report_dir / f"{uuid.uuid4().hex}.md"
    path.write_text(content, encoding="utf-8")
    return path


def run_research(query: str, model: Optional[str], budget: int, *, config: AppConfig) -> dict:
    print(f"[research] starting deep research for '{query}' (budget={budget})")
    plan_text = _ollama_request(
        config.ollama_url,
        model,
        system="You are a research planner producing JSON with tasks and sources.",
        prompt=(
            "Create a JSON object with keys 'tasks' (ordered list of subtasks) and 'sources' (list of URLs) "
            f"for researching: {query}."
        ),
    )
    plan = _parse_plan(plan_text)
    print(f"[research] plan: {json.dumps(plan, ensure_ascii=False)}")

    extra_sources = [url for url in plan.get("sources", []) if isinstance(url, str)]
    from .focused_crawl import run_focused_crawl

    stats = run_focused_crawl(
        query,
        budget,
        use_llm=True,
        model=model,
        config=config,
        extra_seeds=extra_sources,
    )

    docs = stats.get("normalized_docs", [])
    trimmed = [_trim_document(doc) for doc in docs[: budget * 2]]
    context_lines = []
    for idx, doc in enumerate(trimmed, 1):
        context_lines.append(f"Source {idx}: {doc['title'] or doc['url']}")
        context_lines.append(doc["body"])
        context_lines.append(f"URL: {doc['url']}")
    context = "\n\n".join(context_lines)

    report_prompt = (
        "You are a meticulous researcher. Using the provided source snippets, write a markdown report "
        "that answers the query. Include sections, bullet points, and cite sources inline using [^n] markers. "
        "Finish with a References section listing each source URL.\n\n"
        f"Query: {query}\n\nSources:\n{context}"
    )
    report_markdown = _ollama_request(
        config.ollama_url,
        model,
        system="Expert technical researcher producing concise markdown reports.",
        prompt=report_prompt,
    )
    if not report_markdown.strip():
        report_markdown = "# Research Report\n\nUnable to generate a report."

    report_path = _write_report(config.normalized_path.parent / "reports", report_markdown)
    print(f"[research] report written to {report_path}")

    return {
        "plan": plan,
        "stats": stats,
        "report_path": str(report_path),
        "sources": [doc.get("url") for doc in trimmed if doc.get("url")],
    }
