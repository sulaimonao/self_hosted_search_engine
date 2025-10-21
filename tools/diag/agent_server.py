from __future__ import annotations

import json
from wsgiref.simple_server import make_server

from .tool import artifacts, list_probes, run, start_services, stop_services


def app(environ, start_response):
    try:
        path = environ.get("PATH_INFO", "/")
        method = environ.get("REQUEST_METHOD", "GET")
        length = int(environ.get("CONTENT_LENGTH", "0") or 0)
        body = environ["wsgi.input"].read(length).decode("utf-8") if length else ""
        data = json.loads(body) if body else {}

        routes = {
            ("GET", "/probes"): lambda payload: list_probes(),
            ("POST", "/run"): lambda payload: run(payload.get("labels")),
            ("GET", "/artifacts"): lambda payload: artifacts(),
            ("POST", "/start"): lambda payload: start_services(),
            ("POST", "/stop"): lambda payload: stop_services(),
        }
        handler = routes.get((method, path))
        if not handler:
            start_response("404 Not Found", [("Content-Type", "application/json")])
            return [json.dumps({"error": "not_found"}).encode()]

        result = handler(data)
        status = "200 OK" if result.get("exit_code", 0) in (0, None) else "500 Internal Server Error"
        start_response(status, [("Content-Type", "application/json")])
        return [json.dumps(result).encode()]
    except Exception as exc:
        start_response("500 Internal Server Error", [("Content-Type", "application/json")])
        return [json.dumps({"error": repr(exc)}).encode()]


if __name__ == "__main__":
    port = 7070
    print(f"repo_diag agent server listening on http://127.0.0.1:{port}")
    make_server("127.0.0.1", port, app).serve_forever()
