"""Domain profile APIs."""

from __future__ import annotations

from flask import Blueprint, jsonify, request

from ..services.domain_profile import (
    get_graph as get_domain_graph,
    get_page_snapshot,
    get_snapshot as get_domain_snapshot,
    ingest_sample as ingest_domain_sample,
)
from ..services.domain_profiles import get_domain, scan_domain

bp = Blueprint("domains_api", __name__, url_prefix="/api/domains")


@bp.get("/<path:host>")
def read_domain(host: str):
    try:
        profile = get_domain(host)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify(profile)


@bp.post("/scan")
def scan():
    host = request.args.get("host")
    if not host:
        payload = request.get_json(silent=True) or {}
        host_value = payload.get("host")
        host = host_value if isinstance(host_value, str) else None
    if not host:
        return jsonify({"error": "host is required"}), 400
    try:
        profile = scan_domain(host)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify(profile)


@bp.post("/ingest_sample")
def ingest_sample():
    payload = request.get_json(silent=True) or {}
    try:
        summary = ingest_domain_sample(payload)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify(summary)


@bp.get("/snapshot")
def snapshot():
    host = request.args.get("host")
    if not host:
        return jsonify({"error": "host is required"}), 400
    try:
        data = get_domain_snapshot(host)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify(data)


@bp.get("/graph")
def graph():
    host = request.args.get("host")
    if not host:
        return jsonify({"error": "host is required"}), 400
    try:
        limit = int(request.args.get("limit", 150))
    except (TypeError, ValueError):
        limit = 150
    try:
        data = get_domain_graph(host, limit=limit)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify(data)


@bp.get("/page_snapshot")
def page_snapshot():
    url = request.args.get("url")
    if not url:
        return jsonify({"error": "url is required"}), 400
    try:
        data = get_page_snapshot(url)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify(data)


__all__ = [
    "bp",
    "read_domain",
    "scan",
    "ingest_sample",
    "snapshot",
    "graph",
    "page_snapshot",
]
