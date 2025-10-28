"""API endpoints exposing domain clearance profiles."""

from __future__ import annotations

from flask import Blueprint, jsonify, request

from ..db import domain_profiles


bp = Blueprint("domain_profiles", __name__, url_prefix="/api/domain_profiles")


@bp.get("")
@bp.get("/")
def list_domain_profiles():
    try:
        limit = int(request.args.get("limit", 200))
    except (TypeError, ValueError):
        limit = 200
    results = domain_profiles.list_profiles(limit=limit)
    return jsonify({"profiles": results})


@bp.get("/<domain>")
def get_domain_profile(domain: str):
    record = domain_profiles.get(domain)
    if record is None:
        return jsonify({"domain": domain, "found": False}), 404
    payload = dict(record)
    payload["found"] = True
    return jsonify(payload)


__all__ = ["bp", "list_domain_profiles", "get_domain_profile"]
