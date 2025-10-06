"""Meta endpoints exposing server clocks and runtime metadata."""

from __future__ import annotations

import time
from datetime import datetime, timezone

from flask import Blueprint, jsonify

bp = Blueprint("meta_api", __name__, url_prefix="/api/meta")


@bp.get("/time")
def server_time():
    now_utc = datetime.now(timezone.utc)
    local_now = datetime.now().astimezone()
    tz_name = local_now.tzname() or time.tzname[0]
    payload = {
        "server_time": local_now.isoformat(timespec="seconds"),
        "server_time_utc": now_utc.isoformat(timespec="seconds"),
        "server_timezone": tz_name,
        "epoch_ms": int(time.time() * 1000),
    }
    return jsonify(payload), 200


__all__ = ["bp"]
