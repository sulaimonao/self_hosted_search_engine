from app import create_app


def test_health_endpoint():
    app = create_app()
    client = app.test_client()
    response = client.get("/api/healthz")
    assert response.status_code == 200
    assert response.json == {"status": "ok"}
