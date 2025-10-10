"""Metrics endpoint."""

from __future__ import annotations

from flask import Blueprint, Response, jsonify

from prometheus_client import CollectorRegistry, Gauge, CONTENT_TYPE_LATEST, generate_latest

from ..metrics import metrics

bp = Blueprint("metrics_api", __name__)


@bp.get("/metrics")
def metrics_endpoint():
    return jsonify(metrics.snapshot())


def _record_gauge(registry: CollectorRegistry, name: str, value: float, description: str = "") -> None:
    metric = Gauge(name, description or name, registry=registry)
    metric.set(float(value))


@bp.get("/metrics/prometheus")
def metrics_prometheus():
    registry = CollectorRegistry()
    snapshot = metrics.snapshot()

    def _safe(metric_name: str) -> str:
        sanitized = metric_name.replace(".", "_").replace("-", "_")
        return f"self_hosted_{sanitized}"

    for key, value in snapshot.items():
        metric_key = _safe(str(key))
        if isinstance(value, (int, float)):
            _record_gauge(registry, metric_key, float(value))
        elif isinstance(value, dict):
            for sub_key, sub_value in value.items():
                if isinstance(sub_value, (int, float)):
                    _record_gauge(
                        registry,
                        _safe(f"{key}_{sub_key}"),
                        float(sub_value),
                    )
    output = generate_latest(registry)
    return Response(output, mimetype=CONTENT_TYPE_LATEST)
