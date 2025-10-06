from backend.app import create_app


def test_meta_time_endpoint():
    app = create_app()
    client = app.test_client()

    response = client.get("/api/meta/time")
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["server_time"]
    assert payload["server_time_utc"]
    assert payload["server_timezone"]
    assert isinstance(payload["epoch_ms"], int)
