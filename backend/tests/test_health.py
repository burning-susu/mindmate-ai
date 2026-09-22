from fastapi.testclient import TestClient

from mindmate.main import app

client = TestClient(app)


def test_health_returns_service_status() -> None:
    response = client.get("/api/v1/health", headers={"host": "127.0.0.1"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["service"] == "mindmate-backend"


def test_non_local_host_is_rejected() -> None:
    response = client.get("/api/v1/health", headers={"host": "192.168.1.8"})

    assert response.status_code == 400
