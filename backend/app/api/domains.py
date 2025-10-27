"""Domain profile APIs."""

from __future__ import annotations

from flask import Blueprint, jsonify, request

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


__all__ = ["bp", "read_domain", "scan"]
