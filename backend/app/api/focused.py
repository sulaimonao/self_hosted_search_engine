"""Endpoints exposing focused crawl status and logs."""

from __future__ import annotations

from flask import Blueprint, current_app, jsonify

from ..jobs.focused_crawl import FocusedCrawlSupervisor

bp = Blueprint("focused_api", __name__, url_prefix="/api/focused")


@bp.get("/status")
def focused_status():
    supervisor: FocusedCrawlSupervisor = current_app.config["FOCUSED_SUPERVISOR"]
    tail = supervisor.tail_log(lines=50)
    return jsonify({"running": supervisor.is_running(), "log_tail": tail[-50:]})


@bp.get("/last_index_time")
def focused_last_index_time():
    supervisor: FocusedCrawlSupervisor = current_app.config["FOCUSED_SUPERVISOR"]
    return jsonify({"last_index_time": supervisor.last_index_time()})
