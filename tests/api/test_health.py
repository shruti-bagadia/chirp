from fastapi.testclient import TestClient

from app.main import create_app

# Dashboard-page behavior (login required, the Nest queue, etc.) is covered in
# tests/api/test_dashboard.py, which sets up a real DB and a logged-in session.


def test_health_ok():
    client = TestClient(create_app())
    body = client.get("/health").json()
    assert body["status"] == "ok" and body["app"] == "chirp"
