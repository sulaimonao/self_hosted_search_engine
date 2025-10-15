from __future__ import annotations

from app import create_app


def test_research_endpoint_rejects_invalid_budget() -> None:
    app = create_app()
    client = app.test_client()

    response = client.post(
        "/api/research",
        json={"query": "example", "budget": "not-a-number"},
    )

    assert response.status_code == 400
    payload = response.get_json()
    assert payload["error"] == "invalid_budget"
