"""Mission Control graph endpoints."""

from __future__ import annotations

from flask import Blueprint, abort, current_app, jsonify, request

from backend.app.db import AppStateDB


bp = Blueprint("graph_viz", __name__, url_prefix="/api/graph")

PALETTE = {
    "seed": "#D35400",
    "node": "#E67E22",
    "edge": "#8D6E63",
    "leaf": "#D7CCC8",
}


def _state_db() -> AppStateDB:
    state_db = current_app.config.get("APP_STATE_DB")
    if not isinstance(state_db, AppStateDB):
        abort(500, "app state database unavailable")
    return state_db


@bp.get("/network")
def get_network_snapshot():
    limit = request.args.get("limit", type=int) or 2000
    state_db = _state_db()
    snapshot = state_db.graph_network_snapshot(limit=limit)

    nodes = []
    for node in snapshot.get("nodes", []):
        color = node.get("color") or (PALETTE["node"] if node.get("val", 0) >= 4 else PALETTE["leaf"])
        nodes.append({**node, "color": color})

    links = [
        {
            **link,
            "color": PALETTE["edge"],
        }
        for link in snapshot.get("links", [])
    ]

    return jsonify({"nodes": nodes, "links": links})


@bp.get("/hierarchy")
def get_hierarchy_snapshot():
    state_db = _state_db()
    hierarchy = state_db.graph_hierarchy_snapshot()
    return jsonify(hierarchy)
