import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_health_endpoint():
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert "gemini_configured" in data
    assert "monday" in data



def test_reset_endpoint():
    response = client.post("/reset", params={"session_id": "test-session-123"})
    assert response.status_code == 200
    assert response.json() == {"ok": True}


def test_root_index_endpoint():
    response = client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
