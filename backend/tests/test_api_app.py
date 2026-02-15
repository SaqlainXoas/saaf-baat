from __future__ import annotations

from fastapi.testclient import TestClient

from src.api.app import create_app


def test_docs_and_health_endpoints():
    app = create_app()
    client = TestClient(app)

    res = client.get("/health")
    assert res.status_code == 200
    assert res.json() == {"status": "ok"}

    docs = client.get("/docs")
    assert docs.status_code == 200

