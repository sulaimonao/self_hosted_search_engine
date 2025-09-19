"""Metrics endpoint."""

from __future__ import annotations

from flask import Blueprint, jsonify

from ..metrics import metrics

bp = Blueprint("metrics_api", __name__)


@bp.get("/metrics")
def metrics_endpoint():
    return jsonify(metrics.snapshot())
